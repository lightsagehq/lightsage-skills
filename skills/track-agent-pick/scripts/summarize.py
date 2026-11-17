#!/usr/bin/env python3
"""Summarize Lightsage Agent Preference results: win/loss/tie with n, per agent, per period, per prompt.

Usage:
  python3 summarize.py FILE [FILE ...]                    # markdown summary
  python3 summarize.py FILE ... --period week             # periods: day | week (default) | month
  python3 summarize.py FILE ... --split 2026-11-20        # before vs after a date (a page change), Fisher exact
  python3 summarize.py FILE ... --eval EVAL_ID --since 2026-10-01

FILE is saved JSON from any of these (mix freely; attempts are de-duplicated by result id):
  - an Agent Preference results list   (`agent-preference-evals-results-list`; page through all of it)
  - an eval run                        (`evals-get` on a finished run: adds prompts and agent versions)
  - the Agent Preference evals list    (`agent-preference-evals-list`: adds eval and competitor names)

Counting follows Lightsage: win rate = wins / (wins + losses + ties). Attempts with no usable
recommendation (preference_result null, usually errors) are counted separately, never as losses.
"""
import argparse
import datetime as dt
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


def die(msg):
    sys.exit(f"error: {msg}")


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def hyper(x, n1, n2, k):
    return math.comb(n2, x) * math.comb(n1, k - x) / math.comb(n1 + n2, k)


def fisher(a, n1, c, n2, side="two"):
    """a of n1 vs c of n2. side='greater': p that group 2's rate is higher; 'two': two-sided."""
    k = a + c
    lo, hi = max(0, k - n1), min(k, n2)
    if side == "greater":
        return min(1.0, sum(hyper(x, n1, n2, k) for x in range(c, hi + 1)))
    p_obs = hyper(c, n1, n2, k)
    return min(1.0, sum(p for p in (hyper(x, n1, n2, k) for x in range(lo, hi + 1)) if p <= p_obs * (1 + 1e-9)))


def load(files):
    attempts, evals = {}, {}
    for f in files:
        try:
            doc = json.loads(Path(f).read_text())
        except (OSError, ValueError) as e:
            die(f"cannot read {f}: {e}")
        docs = doc if isinstance(doc, list) else [doc]
        for d in docs:
            if not isinstance(d, dict):
                continue
            if "results" in d and isinstance(d["results"], list):  # an eval run
                for r in d["results"]:
                    r = dict(r, eval_id=r.get("eval_id") or d.get("eval_id"), _run=d.get("id"))
                    attempts[r["id"]] = {**attempts.get(r["id"], {}), **{k: v for k, v in r.items() if v is not None}}
                if d.get("eval_id") and d.get("eval_name"):
                    evals.setdefault(d["eval_id"], {"name": d["eval_name"]})
            rows = d.get("data") if isinstance(d.get("data"), list) else ([d] if "preference_result" in d or "competitor" in d else [])
            for r in rows:
                if "competitor" in r or "prompts" in r:  # an eval definition
                    evals[r["id"]] = {"name": r.get("name"), "competitor": (r.get("competitor") or {}).get("name")}
                elif "id" in r and ("preference_result" in r or "eval_id" in r):
                    attempts[r["id"]] = {**attempts.get(r["id"], {}), **{k: v for k, v in r.items() if v is not None}}
    if not attempts:
        die("no attempts found in the files given")
    return list(attempts.values()), evals


def outcome(a):
    pr = a.get("preference_result") or {}
    return pr.get("outcome") or "no_result"


def when(a):
    s = a.get("created_at")
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def period_key(t, period):
    if t is None:
        return "undated"
    if period == "day":
        return t.date().isoformat()
    if period == "month":
        return t.strftime("%Y-%m")
    y, w, _ = t.isocalendar()
    return f"{y}-W{w:02d}"


def wlt(rows):
    c = Counter(outcome(a) for a in rows)
    w, l, t = c["won"], c["lost"], c["tie"]
    return w, l, t, w + l + t, c["no_result"]


def rate_cell(w, n):
    if n == 0:
        return "-"
    lo, hi = wilson(w, n)
    return f"{w / n:.0%} ({lo:.0%}-{hi:.0%})"


def label(eid, evals, rows):
    e = evals.get(eid, {})
    comp = e.get("competitor") or next(((a.get("preference_result") or {}).get("competitor_name") for a in rows if (a.get("preference_result") or {}).get("competitor_name")), None)
    return f"{e.get('name') or eid[:8]}" + (f" (vs {comp})" if comp and comp not in (e.get("name") or "") else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--period", choices=("day", "week", "month"), default="week")
    ap.add_argument("--split", help="ISO date: compare attempts before it with attempts on or after it")
    ap.add_argument("--eval", dest="eval_id")
    ap.add_argument("--since", help="ISO date: ignore older attempts")
    a = ap.parse_args()

    attempts, evals = load(a.files)
    if a.eval_id:
        attempts = [x for x in attempts if x.get("eval_id") == a.eval_id]
    if a.since:
        since = dt.datetime.fromisoformat(a.since).date()
        attempts = [x for x in attempts if when(x) and when(x).date() >= since]
    if not attempts:
        die("no attempts left after filters")

    by_eval = defaultdict(list)
    for x in attempts:
        by_eval[x.get("eval_id") or "?"].append(x)
    dates = sorted(t for t in (when(x) for x in attempts) if t)
    out = ["# Agent preference summary", "",
           f"{len(attempts)} attempts across {len(by_eval)} eval(s)" + (f", {dates[0].date()} to {dates[-1].date()}" if dates else "") + ".",
           "Win rate = wins / (wins + losses + ties), 95% interval in brackets. 'No result' attempts are excluded from n.", ""]

    for eid, rows in sorted(by_eval.items(), key=lambda kv: -len(kv[1])):
        w, l, t, n, nr = wlt(rows)
        out += [f"## {label(eid, evals, rows)}", "", f"Overall: {w} won, {l} lost, {t} tied of {n}; win rate {rate_cell(w, n)}; no result {nr}.", "",
                "| Agent | Won | Lost | Tied | n | Win rate | No result |", "|---|---|---|---|---|---|---|"]
        by_agent = defaultdict(list)
        for x in rows:
            by_agent[x.get("agent") or "unknown"].append(x)
        for ag, rs in sorted(by_agent.items()):
            w, l, t, n, nr = wlt(rs)
            versions = sorted({x.get("agent_version") for x in rs if x.get("agent_version")})
            out.append(f"| {ag}{' (' + ', '.join(versions[-2:]) + ')' if versions else ''} | {w} | {l} | {t} | {n} | {rate_cell(w, n)} | {nr} |")

        periods = sorted({period_key(when(x), a.period) for x in rows})
        if len(periods) >= 2:
            last, prev = periods[-1], periods[-2]
            out += ["", f"### {prev} vs {last}", "", "| Agent | " + prev + " | " + last + " | Change | p (two-sided) |", "|---|---|---|---|---|"]
            for ag, rs in sorted(by_agent.items()):
                p_rows = [x for x in rs if period_key(when(x), a.period) == prev]
                l_rows = [x for x in rs if period_key(when(x), a.period) == last]
                w1, _, _, n1, _ = wlt(p_rows)
                w2, _, _, n2, _ = wlt(l_rows)
                if n1 and n2:
                    out.append(f"| {ag} | {w1}/{n1} {rate_cell(w1, n1)} | {w2}/{n2} {rate_cell(w2, n2)} | {w2 / n2 - w1 / n1:+.0%} | {fisher(w1, n1, w2, n2):.3f} |")
                else:
                    out.append(f"| {ag} | {w1}/{n1} | {w2}/{n2} | - | no data on one side |")
            out.append("")
            out.append("All periods: " + ", ".join(f"{p} {wlt([x for x in rows if period_key(when(x), a.period) == p])[0]}/{wlt([x for x in rows if period_key(when(x), a.period) == p])[3]}" for p in periods))

        with_prompt = [x for x in rows if x.get("prompt")]
        if with_prompt:
            out += ["", "### Per prompt (from eval runs)", "", "| Prompt | Agent | W-L-T | Picked instead |", "|---|---|---|---|"]
            groups = defaultdict(list)
            for x in with_prompt:
                groups[(x["prompt"], x.get("agent") or "unknown")].append(x)
            for (pr, ag), rs in sorted(groups.items(), key=lambda kv: (wlt(kv[1])[0] / max(1, wlt(kv[1])[3]), kv[0])):
                w, l, t, n, nr = wlt(rs)
                winners = Counter((x.get("preference_result") or {}).get("winner_name") for x in rs if outcome(x) == "lost")
                short = pr if len(pr) <= 70 else pr[:67] + "..."
                out.append(f"| {short} | {ag} | {w}-{l}-{t} | {', '.join(f'{k} {v}' for k, v in winners.most_common(2) if k) or '-'} |")

        if a.split:
            cut = dt.datetime.fromisoformat(a.split).date()
            out += ["", f"### Before vs on/after {cut} (one-sided Fisher: after > before)", "", "| Agent | Before | After | Change | p |", "|---|---|---|---|---|"]
            for ag, rs in sorted(by_agent.items()):
                b = [x for x in rs if when(x) and when(x).date() < cut]
                f = [x for x in rs if when(x) and when(x).date() >= cut]
                w1, _, _, n1, _ = wlt(b)
                w2, _, _, n2, _ = wlt(f)
                if n1 and n2:
                    out.append(f"| {ag} | {w1}/{n1} {rate_cell(w1, n1)} | {w2}/{n2} {rate_cell(w2, n2)} | {w2 / n2 - w1 / n1:+.0%} | {fisher(w1, n1, w2, n2, 'greater'):.3f} |")
                else:
                    out.append(f"| {ag} | {w1}/{n1} | {w2}/{n2} | - | no data on one side |")
        out.append("")

    small = [ag for rows in by_eval.values() for ag, rs in Counter(x.get("agent") for x in rows).items() if rs < 9]
    if small:
        out.append("Note: some agents have fewer than 9 comparisons in an eval (3 prompts x 3 runs); treat their rates as directional.")
    print("\n".join(out))


if __name__ == "__main__":
    main()
