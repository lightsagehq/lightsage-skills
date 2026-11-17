#!/usr/bin/env python3
"""Tally agent-pick runs into pick share per agent, with n and 95% intervals.

Usage:
  python3 tally.py OUT --sheet                 # write OUT/judgments.json (auto picks) + OUT/judge-sheet.md
  python3 tally.py OUT                         # markdown report to stdout (and OUT/report.md)
  python3 tally.py OUT --json                  # the same numbers as JSON
  python3 tally.py --compare BEFORE AFTER      # brand pick share before vs after a page change, Fisher exact test

OUT is the folder run_agents.py wrote. Picks come from OUT/judgments.json when present; any run still
marked "judged": false uses the automatic guess and is flagged in the report. Judge before you report.

judgments.json, one entry per run id ("<agent>/<task>/r<k>"):
  pick       vendor the agent chose as its primary choice (installed, or stated default), "none", or another name
  pick_type  sole | split (one of 2-3 options split by a condition) | none
  reason     one line in the agent's own words: why it chose what it chose
  code       for runs the brand lost: a b c d t e (see references/reading-runs.md)
  stall      where the run stopped short, if it did ("" if not)
  judged     true once a person or judge agent has checked it
"""
import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REC_RE = re.compile(r"\b(recommend|go with|i'?d (?:use|pick|choose)|use|pick|choose|default|best (?:choice|option|fit)|winner|my pick)\b", re.I)


def die(msg):
    sys.exit(f"error: {msg}")


def load(out):
    out = Path(out)
    spec_path = out / "tasks.json"
    if not spec_path.exists():
        die(f"{spec_path} not found: is {out} a run_agents.py output folder?")
    spec = json.loads(spec_path.read_text())
    runs = {}
    for meta_path in sorted(out.glob("runs/*/*/r*/meta.json")):
        meta = json.loads(meta_path.read_text())
        rid = f"{meta['agent']}/{meta['task_id']}/r{meta['run']}"
        meta["_dir"] = meta_path.parent
        runs[rid] = meta
    if not runs:
        die(f"no runs under {out}/runs")
    return spec, runs


def vendors(spec):
    vs = [dict(spec["brand"], _brand=True)] + [dict(c, _brand=False) for c in spec.get("competitors", [])]
    for v in vs:
        terms = [v["name"]] + v.get("aliases", [])
        v["_name_re"] = re.compile(r"(?<![\w-])(" + "|".join(re.escape(t) for t in terms if t) + r")(?![\w-])", re.I)
        pk = [p for p in v.get("packages", []) + v.get("domains", []) if p]
        v["_code_re"] = re.compile(r"(?<![\w@/.-])(" + "|".join(re.escape(p) for p in pk) + r")(?![\w-])", re.I) if pk else None
    return vs


def added_lines(diff):
    return "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))


def auto_pick(meta, vs):
    answer = (meta["_dir"] / "answer.md").read_text(errors="replace")
    diff = (meta["_dir"] / "diff.txt").read_text(errors="replace") if (meta["_dir"] / "diff.txt").exists() else ""
    code = added_lines(diff) + "\n" + "\n".join(meta.get("installs", []))
    in_code = Counter()
    for v in vs:
        hits = len(v["_code_re"].findall(code)) if v["_code_re"] else 0
        hits += len(v["_name_re"].findall(code))
        if hits:
            in_code[v["name"]] = hits
    mentioned = {}
    for v in vs:
        m = v["_name_re"].search(answer)
        if m:
            mentioned[v["name"]] = m.start()
    if in_code:
        top = in_code.most_common()
        ptype = "sole" if len(top) == 1 else "split"
        return top[0][0], ptype, "code", sorted(mentioned)
    for sentence in re.split(r"(?<=[.!?\n])\s+", answer):
        if REC_RE.search(sentence):
            named = [(v["_name_re"].search(sentence).start(), v["name"]) for v in vs if v["_name_re"].search(sentence)]
            if named:
                return min(named)[1], "sole" if len(named) == 1 else "split", "answer", sorted(mentioned)
    if mentioned:
        return min(mentioned, key=mentioned.get), "sole", "first-mention", sorted(mentioned)
    return "none", "none", "nothing-matched", []


def write_sheet(out, spec, runs):
    vs = vendors(spec)
    jpath = Path(out) / "judgments.json"
    old = json.loads(jpath.read_text()) if jpath.exists() else {}
    judgments, lines = {}, ["# Judge sheet", "", f"Brand: {spec['brand']['name']}. Vendors: " + ", ".join(v["name"] for v in vs), "",
                            "For each run read answer.md and diff.txt in its folder (not this sheet's guess) and fix the entry in judgments.json.", ""]
    for rid, meta in sorted(runs.items()):
        pick, ptype, source, mentioned = auto_pick(meta, vs)
        prev = old.get(rid)
        if prev and prev.get("judged"):
            judgments[rid] = prev
        else:
            judgments[rid] = {"pick": pick, "pick_type": ptype, "reason": "", "code": "", "stall": "", "judged": False, "auto_source": source}
        lines += [f"## {rid}  [{meta['status']}]", f"- task ({meta.get('kind')}): {meta['prompt'][:160]}",
                  f"- folder: {meta['_dir']}", f"- auto pick: {pick} ({ptype}, from {source}); named: {', '.join(mentioned) or '-'}",
                  f"- installs: {'; '.join(meta.get('installs', [])) or '-'}", f"- fetched: {len(meta.get('fetched', []))} urls, {len(meta.get('fetch_errors', []))} errors", ""]
    jpath.write_text(json.dumps(judgments, indent=2) + "\n")
    (Path(out) / "judge-sheet.md").write_text("\n".join(lines))
    todo = sum(1 for j in judgments.values() if not j.get("judged"))
    print(f"wrote {jpath} ({len(judgments)} runs, {todo} to judge) and {Path(out) / 'judge-sheet.md'}")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt(k, n):
    if n == 0:
        return "-"
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({k / n:.0%}, {lo:.0%}-{hi:.0%})"


def fisher_greater(a, b, c, d):
    """One-sided p that group 2 (c of c+d) has a higher rate than group 1 (a of a+b)."""
    n1, n2, k = a + b, c + d, a + c
    total = math.comb(n1 + n2, k)
    p = 0.0
    for x in range(c, min(k, n2) + 1):
        if k - x <= n1:
            p += math.comb(n2, x) * math.comb(n1, k - x) / total
    return min(1.0, p)


def collect(spec, runs, judgments):
    brand = spec["brand"]["name"]
    vs = vendors(spec)
    rows = []
    for rid, meta in runs.items():
        j = judgments.get(rid)
        if j is None:
            pick, ptype, source, _ = auto_pick(meta, vs)
            j = {"pick": pick, "pick_type": ptype, "judged": False, "reason": "", "code": "", "stall": ""}
        answer = (meta["_dir"] / "answer.md").read_text(errors="replace")
        rows.append({"id": rid, "agent": meta["agent"], "version": meta.get("agent_version"), "task": meta["task_id"],
                     "kind": meta.get("kind"), "status": meta["status"], "pick": j.get("pick") or "none",
                     "pick_type": j.get("pick_type") or "none", "judged": bool(j.get("judged")), "reason": j.get("reason", ""),
                     "code": j.get("code", ""), "stall": j.get("stall", ""),
                     "brand_named": bool(vs[0]["_name_re"].search(answer)), "fetched": meta.get("fetched", []),
                     "fetch_errors": meta.get("fetch_errors", []), "denied": meta.get("denied", []), "secs": meta.get("secs")})
    return brand, rows


def usable(r):
    return r["status"] in ("ok", "empty")


def domain(url):
    m = re.match(r"https?://([^/]+)", url)
    return (m.group(1).lower().removeprefix("www.") if m else url)


def report(out, as_json=False):
    spec, runs = load(out)
    jpath = Path(out) / "judgments.json"
    judgments = json.loads(jpath.read_text()) if jpath.exists() else {}
    brand, rows = collect(spec, runs, judgments)
    brand_domains = [d.lower() for d in spec["brand"].get("domains", [])]
    agents = sorted({r["agent"] for r in rows})
    good = [r for r in rows if usable(r)]
    names = [spec["brand"]["name"]] + [c["name"] for c in spec.get("competitors", [])]
    others = sorted({r["pick"] for r in good if r["pick"] not in names and r["pick"] != "none"})
    data = {"brand": brand, "agents": {}, "unjudged": sum(1 for r in good if not r["judged"]),
            "failed": Counter(r["status"] for r in rows if not usable(r))}
    L = [f"# Agent pick: {brand} ({spec.get('category', '')})", ""]
    versions = {r["agent"]: r["version"] for r in rows}
    per_task = Counter((r["agent"], r["task"]) for r in good)
    L.append(f"{len(spec['tasks'])} tasks; agents: " + ", ".join(f"{a} ({versions[a]})" for a in agents)
             + f"; {len(rows)} sessions, {len(good)} usable" + (f", failed: {dict(data['failed'])}" if data["failed"] else ""))
    if data["unjudged"]:
        L.append(f"\n**{data['unjudged']} of {len(good)} picks are automatic guesses, not judged.** Run --sheet and judge before you report.")
    if per_task and min(per_task.values()) < 3:
        L.append("\n**Some task-agent pairs have fewer than 3 usable runs; read those rows as anecdotes.**")
    L += ["", "## Pick share (primary choice; split picks count for the vendor named first)", "",
          "| Vendor | " + " | ".join(agents) + " | All |", "|---|" + "---|" * (len(agents) + 1)]
    for v in names + others + ["none"]:
        cells = []
        for a in agents + ["*"]:
            sub = [r for r in good if a == "*" or r["agent"] == a]
            cells.append(fmt(sum(1 for r in sub if r["pick"] == v), len(sub)))
        label = f"**{v}**" if v == brand else v
        L.append(f"| {label} | " + " | ".join(cells) + " |")
    L += ["", "## Brand detail", "", "| Agent | n | Picked (sole) | Picked (split) | Named in answer | Ask tasks | Build tasks |", "|---|---|---|---|---|---|---|"]
    for a in agents + ["*"]:
        sub = [r for r in good if a == "*" or r["agent"] == a]
        n = len(sub)
        sole = sum(1 for r in sub if r["pick"] == brand and r["pick_type"] == "sole")
        split = sum(1 for r in sub if r["pick"] == brand and r["pick_type"] == "split")
        named = sum(1 for r in sub if r["brand_named"])
        by_kind = []
        for kind in ("ask", "build"):
            ks = [r for r in sub if r["kind"] == kind]
            by_kind.append(fmt(sum(1 for r in ks if r["pick"] == brand), len(ks)))
        data["agents"][a] = {"n": n, "brand_sole": sole, "brand_split": split, "brand_named": named}
        L.append(f"| {'All' if a == '*' else a} | {n} | {fmt(sole, n)} | {fmt(split, n)} | {fmt(named, n)} | {by_kind[0]} | {by_kind[1]} |")
    L += ["", "## Per task (brand picks / usable runs, then who won most)", "", "| Task | Kind | " + " | ".join(agents) + " |", "|---|---|" + "---|" * len(agents)]
    losing = []
    for t in spec["tasks"]:
        cells = []
        for a in agents:
            sub = [r for r in good if r["agent"] == a and r["task"] == t["id"]]
            if not sub:
                cells.append("-")
                continue
            k = sum(1 for r in sub if r["pick"] == brand)
            top = Counter(r["pick"] for r in sub).most_common(1)[0]
            cells.append(f"{k}/{len(sub)} · {top[0]} {top[1]}")
            if top[0] != brand and k < len(sub) / 2:
                losing.append((t["id"], a, top[0]))
        L.append(f"| {t['id']} | {t.get('kind', '')} | " + " | ".join(cells) + " |")
    L += ["", "## Losing patterns", ""]
    codes = Counter(r["code"] for r in good if r["pick"] != brand and r["code"])
    if codes:
        L.append("Loss codes: " + ", ".join(f"{c} = {n}" for c, n in codes.most_common()) + " (a unreachable, b missing how-to, c commercial, d no product, t tie, e never looked)")
    L.append(f"Tasks the brand loses (competitor wins most runs): {', '.join(f'{t}@{a}→{w}' for t, a, w in losing) or 'none'}")
    reasons = [r for r in good if r["pick"] != brand and r["reason"]]
    for r in reasons[:25]:
        L.append(f"- {r['id']} → {r['pick']}: {r['reason']}" + (f" [{r['code']}]" if r["code"] else ""))
    if not reasons:
        L.append("- (no reasons recorded yet: fill `reason` in judgments.json)")
    L += ["", "## Docs agents fetched", ""]
    fetched = Counter(domain(u) for r in good for u in r["fetched"])
    L.append("Top domains: " + (", ".join(f"{d} {n}" for d, n in fetched.most_common(12)) or "none recorded"))
    brand_fetch = Counter(u for r in good for u in r["fetched"] if any(bd in u.lower() for bd in brand_domains))
    L.append("Brand pages fetched: " + (", ".join(f"{u} ({n})" for u, n in brand_fetch.most_common(10)) or "none"))
    errs = Counter((e["url"], e["error"][:80]) for r in good for e in r["fetch_errors"])
    if errs:
        L.append("Fetch errors: ")
        for (u, e), n in errs.most_common(12):
            flag = " **(brand)**" if any(bd in u.lower() for bd in brand_domains) else ""
            L.append(f"- {u}{flag} x{n}: {e}")
    stalls = Counter(r["stall"] for r in good if r["stall"])
    timeouts = sum(1 for r in rows if r["status"] == "timeout")
    denied = sum(1 for r in good if r["denied"])
    L += ["", "## Stalls", "", f"Timeouts: {timeouts}. Runs with permission denials (harness limit, not a vendor stall): {denied}."]
    for s, n in stalls.most_common(10):
        L.append(f"- {s} x{n}")
    text = "\n".join(L) + "\n"
    if as_json:
        data["rows"] = [{k: v for k, v in r.items() if k not in ("fetched",)} for r in rows]
        print(json.dumps(data, indent=2, default=str))
    else:
        (Path(out) / "report.md").write_text(text)
        print(text)


def compare(before, after):
    spec_b, runs_b = load(before)
    spec_a, runs_a = load(after)
    brand = spec_a["brand"]["name"]

    def picks(out, spec, runs):
        jp = Path(out) / "judgments.json"
        j = json.loads(jp.read_text()) if jp.exists() else {}
        return collect(spec, runs, j)[1]

    rb, ra = picks(before, spec_b, runs_b), picks(after, spec_a, runs_a)
    common = {r["task"] for r in rb} & {r["task"] for r in ra}
    unj = sum(1 for r in rb + ra if usable(r) and not r["judged"])
    print(f"# Before vs after: {brand}\n\nTasks in both: {len(common)}. One-sided Fisher exact test (after > before).")
    if unj:
        print(f"\n**{unj} picks are automatic guesses, not judged.** Judge both folders together, without telling the judge which is which.")
    print("\n| Agent | Before | After | Change | p |\n|---|---|---|---|---|")
    for a in sorted({r["agent"] for r in rb + ra}):
        b = [r for r in rb if r["agent"] == a and r["task"] in common and usable(r)]
        f = [r for r in ra if r["agent"] == a and r["task"] in common and usable(r)]
        kb, ka = sum(r["pick"] == brand for r in b), sum(r["pick"] == brand for r in f)
        if not b or not f:
            continue
        p = fisher_greater(kb, len(b) - kb, ka, len(f) - ka)
        print(f"| {a} | {fmt(kb, len(b))} | {fmt(ka, len(f))} | {ka / len(f) - kb / len(b):+.0%} | {p:.3f} |")
    print("\nCall it a win only at p < 0.05 with at least 3 runs per task on each side, and confirm on a fresh rerun.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("out", nargs="?")
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    a = ap.parse_args()
    if a.compare:
        compare(*a.compare)
    elif not a.out:
        ap.error("give OUT, or --compare BEFORE AFTER")
    elif a.sheet:
        spec, runs = load(a.out)
        write_sheet(a.out, spec, runs)
    else:
        report(a.out, a.json)


if __name__ == "__main__":
    main()
