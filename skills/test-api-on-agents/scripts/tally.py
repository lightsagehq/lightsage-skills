#!/usr/bin/env python3
"""Tally a run folder into pass rates per task x agent, with n, a 95% interval,
time, turns, tool calls, and the stall signals seen in failed attempts.

  python3 tally.py agent-test-runs/acme-20261117-101500          # markdown to stdout
  python3 tally.py <out-dir> --json > summary.json               # machine-readable
  python3 tally.py <out-dir> --cleanup                           # delete temp work dirs

Pass = the task's check exited 0. Harness errors (agent not logged in, setup
failed, runner crash) are not counted in n; they are listed separately.
Timeouts count as failures. Signals are regex hints from tool output, not a
diagnosis: read the transcripts they point to before naming a cause.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def med(xs: List[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def fmt_s(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{x:.0f}s" if x < 120 else f"{x / 60:.1f}m"


def fmt_n(x: Optional[float]) -> str:
    return "-" if x is None else (f"{x:.0f}" if float(x).is_integer() else f"{x:.1f}")


def load(out: Path) -> List[Dict[str, Any]]:
    rows = []
    for mp in sorted(out.glob("*/*/run-*/meta.json")):
        m = json.loads(mp.read_text())
        cp = mp.parent / "check.json"
        m["_check"] = json.loads(cp.read_text()) if cp.exists() else None
        m["_dir"] = str(mp.parent)
        rows.append(m)
    return rows


def outcome(m: Dict[str, Any]) -> str:
    if m.get("status") == "harness_error":
        return "harness_error"
    c = m.get("_check")
    if c is None or c.get("passed") is None:
        return "unchecked"
    return "pass" if c["passed"] else ("timeout" if m.get("timed_out") else "fail")


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    cells: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for m in rows:
        cells[(m["task"], m["agent"])].append(m)
    table = []
    for (task, agent), ms in sorted(cells.items()):
        scored = [m for m in ms if outcome(m) in ("pass", "fail", "timeout")]
        k = sum(1 for m in scored if outcome(m) == "pass")
        n = len(scored)
        lo, hi = wilson(k, n)
        fail_sig: Counter = Counter()
        for m in scored:
            if outcome(m) != "pass":
                for s in (m.get("signals") or {}):
                    fail_sig[s] += 1
        table.append({
            "task": task, "agent": agent, "passed": k, "n": n,
            "rate": (k / n) if n else None, "ci95": [round(lo, 2), round(hi, 2)],
            "median_sec": med([m.get("duration_sec") for m in scored]),
            "median_turns": med([m.get("turns") for m in scored]),
            "median_tool_calls": med([m.get("tool_calls") for m in scored]),
            "timeouts": sum(1 for m in scored if outcome(m) == "timeout"),
            "harness_errors": sum(1 for m in ms if outcome(m) == "harness_error"),
            "unchecked": sum(1 for m in ms if outcome(m) == "unchecked"),
            "failure_signals": dict(fail_sig.most_common()),
            "failed_attempts": [m["_dir"] for m in scored if outcome(m) != "pass"],
        })
    agents: Dict[str, Dict[str, int]] = defaultdict(lambda: {"passed": 0, "n": 0})
    for r in table:
        agents[r["agent"]]["passed"] += r["passed"]
        agents[r["agent"]]["n"] += r["n"]
    sig_attempts: Counter = Counter()
    sig_tasks: Dict[str, set] = defaultdict(set)
    bad_urls: Counter = Counter()
    for m in rows:
        if outcome(m) in ("fail", "timeout"):
            for s in (m.get("signals") or {}):
                sig_attempts[s] += 1
                sig_tasks[s].add(m["task"])
            for u in m.get("failing_urls") or []:
                bad_urls[u] += 1
    harness = [{"dir": m["_dir"], "error": m.get("harness_error")} for m in rows if outcome(m) == "harness_error"]
    workdirs = sorted({str(Path(m["workdir"]).parent) for m in rows if m.get("workdir")})
    return {"cells": table,
            "agents": {a: dict(v, rate=(v["passed"] / v["n"]) if v["n"] else None,
                               ci95=[round(x, 2) for x in wilson(v["passed"], v["n"])]) for a, v in agents.items()},
            "failure_signals": [{"signal": s, "failed_attempts": c, "tasks": sorted(sig_tasks[s])}
                                for s, c in sig_attempts.most_common()],
            "failing_urls": [{"url": u, "attempts": c} for u, c in bad_urls.most_common(25)],
            "harness_errors": harness, "workdirs": workdirs}


def markdown(s: Dict[str, Any], out: Path) -> str:
    L = [f"# Agent task results: {out.name}", ""]
    total_n = sum(c["n"] for c in s["cells"])
    L.append("## By agent")
    L.append("| Agent | Passed | n | Rate | 95% interval |")
    L.append("|---|---:|---:|---:|---|")
    for a, v in sorted(s["agents"].items()):
        rate = "-" if v["rate"] is None else f"{v['rate']:.0%}"
        L.append(f"| {a} | {v['passed']} | {v['n']} | {rate} | {v['ci95'][0]:.0%}-{v['ci95'][1]:.0%} |")
    L += ["", "## By task and agent",
          "| Task | Agent | Pass/n | 95% interval | Median time | Median turns | Median tool calls | Timeouts | Signals in failures |",
          "|---|---|---:|---|---:|---:|---:|---:|---|"]
    for c in s["cells"]:
        sig = ", ".join(f"{k} x{v}" for k, v in c["failure_signals"].items()) or "-"
        L.append(f"| {c['task']} | {c['agent']} | {c['passed']}/{c['n']} | {c['ci95'][0]:.0%}-{c['ci95'][1]:.0%} | "
                 f"{fmt_s(c['median_sec'])} | {fmt_n(c['median_turns'])} | {fmt_n(c['median_tool_calls'])} | "
                 f"{c['timeouts']} | {sig} |")
    if any(c["n"] < 3 for c in s["cells"]):
        L += ["", "Some cells have n < 3: report them as smoke results, not rates."]
    if s["failure_signals"]:
        L += ["", "## Stall signals across failed attempts (hints, confirm in transcripts)",
              "| Signal | Failed attempts | Tasks |", "|---|---:|---|"]
        for f in s["failure_signals"]:
            L.append(f"| {f['signal']} | {f['failed_attempts']} | {', '.join(f['tasks'])} |")
    if s["failing_urls"]:
        L += ["", "## URLs that errored in failed attempts", "| URL | Attempts |", "|---|---:|"]
        for u in s["failing_urls"]:
            L.append(f"| {u['url']} | {u['attempts']} |")
    failed = [(c["task"], c["agent"], d) for c in s["cells"] for d in c["failed_attempts"]]
    if failed:
        L += ["", "## Failed attempts to read (events.jsonl first, transcript.jsonl for detail)"]
        for t, a, d in failed[:40]:
            L.append(f"- {t} / {a}: {d}")
    if s["harness_errors"]:
        L += ["", f"## Harness errors (excluded from n): {len(s['harness_errors'])}"]
        for h in s["harness_errors"][:20]:
            L.append(f"- {h['dir']}: {h['error']}")
    L += ["", f"Scored attempts: {total_n}. Work dirs are kept for re-checks; "
          f"delete with: python3 {Path(__file__).name} {out} --cleanup"]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir")
    ap.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    ap.add_argument("--cleanup", action="store_true", help="delete the temp work dirs of this run folder")
    args = ap.parse_args(argv)
    out = Path(args.out_dir).resolve()
    rows = load(out)
    if not rows:
        print(f"ERROR: no attempts found under {out}", file=sys.stderr)
        return 2
    s = summarize(rows)
    if args.cleanup:
        for d in s["workdirs"]:
            shutil.rmtree(d, ignore_errors=True)
        print(f"Deleted {len(s['workdirs'])} work dirs. Transcripts in {out} are kept.")
        return 0
    (out / "summary.json").write_text(json.dumps(s, indent=2))
    print(json.dumps(s, indent=2) if args.json else markdown(s, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
