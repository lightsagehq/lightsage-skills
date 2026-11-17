#!/usr/bin/env python3
"""Build the evidence table for fixing AI answers: lost answers, the sources cited where you lose,
owned pages cited without a win, and claims about you to check.

Inputs (pick one):
  --lightsage FILE   Lightsage prompt runs as returned by the prompts-runs-retrieve tool
                     (JSON array, JSONL, or {"data": [...]}); needs --brand
  --extracted FILE   extracted.jsonl from measure-ai-visibility's tally.py extract
                     (optionally --labels labels.jsonl from tally.py labels)

Examples
  python3 evidence.py --lightsage runs.json --brand "Acme Mail" --out evidence.md --json evidence.json
  python3 evidence.py --extracted extracted.jsonl --labels labels.jsonl --out evidence.md
"""
import argparse
import collections
import json
import re
import sys
import urllib.parse

CLAIM_RE = re.compile(r"(\$|\d|free|only|doesn'?t|does not|no longer|lacks?|limit|pricing|price|support|"
                      r"deprecat|shut|acquired|cannot|can'?t|requires?|not available)", re.I)


def load(path):
    text = open(path, encoding="utf-8").read().strip()
    if not text:
        return []
    if text[0] in "[{":
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                obj = obj.get("data") or obj.get("results") or [obj]
            return obj
        except ValueError:
            pass
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def host(url):
    try:
        h = urllib.parse.urlparse(url or "").hostname or ""
    except ValueError:
        h = ""
    return h.lower().removeprefix("www.")


def norm_lightsage(rows, brand, domain):
    out = []
    b = brand.lower()
    for r in rows:
        mentions = r.get("mentions") or []
        own, comps, comp_rec, comp_domains = None, [], [], {}
        for m in mentions:
            br = m.get("brand") or {}
            name = br.get("name") or ""
            d = (br.get("domain") or "").lower().removeprefix("www.")
            if name.lower() == b or (domain and d and d == domain):
                own = m
            elif name:
                comps.append(name)
                if m.get("is_recommended"):
                    comp_rec.append(name)
                if d:
                    comp_domains[d] = name
        own_mentioned = r.get("is_brand_mentioned")
        if own_mentioned is None:
            own_mentioned = own is not None
        cites = []
        for c in r.get("citations") or []:
            d = (c.get("domain") or host(c.get("url"))).lower().removeprefix("www.")
            owner = "own" if c.get("is_company_link") else comp_domains.get(d, "third-party")
            cites.append({"url": c.get("url"), "domain": d, "owner": owner})
        p = r.get("prompt") or {}
        engine = r.get("agent") or r.get("harness") or (r.get("platform") or {}).get("name") or "unknown"
        if r.get("model_id") and r.get("target_kind") == "coding_agent" and r["model_id"] not in engine:
            engine += f" ({r['model_id']})"
        out.append({"id": r.get("id"), "prompt_id": r.get("prompt_id"), "prompt": p.get("text", ""),
                    "topic": (p.get("topic") or {}).get("name"), "engine": engine,
                    "date": (r.get("run_date") or "")[:10], "own_mentioned": bool(own_mentioned),
                    "own_recommended": (own or {}).get("is_recommended"),
                    "own_sentiment": (own or {}).get("sentiment"), "own_quote": (own or {}).get("quote"),
                    "wrong_claim": None, "competitors": comps, "competitors_recommended": comp_rec,
                    "citations": cites, "has_full_response": r.get("response") is not None})
    return out


def norm_extracted(rows, labels):
    out = []
    for r in rows:
        if (r.get("intent") or "").lower() == "control":
            continue
        key = f"{r['prompt_id']}|{r['engine']}|{r['run']}"
        lab = labels.get(key, {})
        own = next((m for m in r.get("mentions", []) if m.get("is_own")), None)
        out.append({"id": key.replace("|", "/"), "prompt_id": r["prompt_id"], "prompt": r.get("prompt", ""), "topic": r.get("intent"),
                    "engine": r["engine"], "date": (r.get("ts") or "")[:10],
                    "own_mentioned": r.get("brand_mentioned", own is not None),
                    "own_recommended": lab.get("recommended"), "own_sentiment": lab.get("sentiment"),
                    "own_quote": (own or {}).get("quote"), "wrong_claim": lab.get("wrong_claim"),
                    "competitors": r.get("competitors_mentioned", []), "competitors_recommended": [],
                    "citations": [{"url": c.get("url"), "domain": c.get("domain"), "owner": c.get("owner", "third-party")}
                                  for c in r.get("citations", [])],
                    "has_full_response": True})
    return out


def lost(r):
    """Lost = a competitor shows up and you are absent, or you are named but explicitly not recommended."""
    if not r["competitors"]:
        return False
    return (not r["own_mentioned"]) or r["own_recommended"] is False


def won(r):
    return r["own_mentioned"] and r["own_recommended"] is not False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--lightsage")
    src.add_argument("--extracted")
    ap.add_argument("--brand", help="your brand name as Lightsage stores it (required with --lightsage)")
    ap.add_argument("--domain", help="your main domain, e.g. acme.com (optional)")
    ap.add_argument("--labels", help="labels.jsonl from tally.py labels (with --extracted)")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--out")
    ap.add_argument("--json")
    a = ap.parse_args()

    if a.lightsage:
        if not a.brand:
            sys.exit("error: --brand is required with --lightsage")
        rows = norm_lightsage(load(a.lightsage), a.brand, (a.domain or "").lower().removeprefix("www."))
    else:
        labels = {l["key"]: l for l in load(a.labels)} if a.labels else {}
        rows = norm_extracted(load(a.extracted), labels)
    if not rows:
        sys.exit("no answers in input")

    L = ["# Answer evidence\n"]
    dates = sorted(r["date"] for r in rows if r["date"])
    prompts = {r["prompt_id"] for r in rows}
    engines = sorted({r["engine"] for r in rows})
    partial = sum(1 for r in rows if not r["has_full_response"])
    L.append(f"Scope: {len(rows)} answers, {len(prompts)} prompts, engines: {', '.join(engines)}"
             + (f", {dates[0]} to {dates[-1]}" if dates else "") + ".")
    if partial:
        L.append(f"{partial} answers are summaries without full text: retrieve them before quoting claims.")
    n_lost, n_won = sum(map(lost, rows)), sum(map(won, rows))
    L.append(f"Lost (competitor present, you absent or not recommended): {n_lost}. Won (you named): {n_won}.\n")

    # A. lost prompts
    by_prompt = collections.defaultdict(list)
    for r in rows:
        by_prompt[r["prompt_id"]].append(r)
    lost_prompts = []
    for pid, v in by_prompt.items():
        lv = [r for r in v if lost(r)]
        if not lv:
            continue
        comp = collections.Counter(c for r in lv for c in set(r["competitors"]))
        lost_prompts.append({"prompt_id": pid, "prompt": v[0]["prompt"], "topic": v[0]["topic"],
                             "lost": len(lv), "answers": len(v),
                             "engines": sorted({r["engine"] for r in lv}),
                             "competitors": comp.most_common(4), "ids": [r["id"] for r in lv][:5]})
    lost_prompts.sort(key=lambda x: (-x["lost"], -x["answers"]))
    L.append("## Prompts you lose most\n")
    if lost_prompts:
        L.append("| Prompt | Lost / answers | Engines | Who wins (answers) | Example run ids |")
        L.append("|---|---|---|---|---|")
        for x in lost_prompts[: a.top]:
            L.append(f"| {x['prompt'][:90]} | {x['lost']}/{x['answers']} | {', '.join(x['engines'])} | "
                     + ", ".join(f"{c} {k}" for c, k in x["competitors"]) + f" | {', '.join(map(str, x['ids']))} |")
    else:
        L.append("No lost answers in this scope.")

    # B. source targets: domains cited where you lose, vs where you win
    dl, dw, urls = collections.defaultdict(set), collections.Counter(), collections.defaultdict(collections.Counter)
    owner_of = {}
    for r in rows:
        ds = {c["domain"]: c for c in r["citations"] if c["domain"]}
        for d, c in ds.items():
            owner_of[d] = c["owner"]
            if lost(r):
                dl[d].add(r["prompt_id"])
                urls[d][c["url"]] += 1
            if won(r):
                dw[d] += 1
    targets = sorted(dl, key=lambda d: (-len(dl[d]), -sum(urls[d].values()), d))
    L.append("\n## Sources cited where you lose\n")
    if targets:
        L.append(f"Won answers: {n_won}. A domain cited about as often when you win is not what separates you.\n")
        L.append("| Domain | Owner | Lost prompts | Lost answers citing | Won answers citing | Most cited URL |")
        L.append("|---|---|---|---|---|---|")
        for d in targets[: a.top]:
            top_url = urls[d].most_common(1)[0][0]
            L.append(f"| {d} | {owner_of[d]} | {len(dl[d])} | {sum(urls[d].values())} | {dw[d]} | {top_url} |")
    else:
        L.append("No citations on lost answers (the engine may have answered from memory: fix owned and third-party facts, then re-measure).")

    # C. owned pages cited without a win
    owned = collections.defaultdict(lambda: {"cited": 0, "not_named": 0, "ids": []})
    for r in rows:
        for c in r["citations"]:
            if c["owner"] == "own":
                x = owned[c["url"]]
                x["cited"] += 1
                if not won(r):
                    x["not_named"] += 1
                    x["ids"].append(r["id"])
    L.append("\n## Your pages cited (and how often the answer still left you out)\n")
    if owned:
        L.append("| URL | Answers citing | Of those, you not named or not recommended | Run ids |")
        L.append("|---|---|---|---|")
        for u, x in sorted(owned.items(), key=lambda kv: (-kv[1]["not_named"], -kv[1]["cited"]))[: a.top]:
            L.append(f"| {u} | {x['cited']} | {x['not_named']} | {', '.join(map(str, x['ids'][:4]))} |")
    else:
        L.append("None of your pages were cited.")

    # D. claims to check
    claims = [r for r in rows if r["own_quote"] and (CLAIM_RE.search(r["own_quote"]) or r["wrong_claim"]
                                                     or (r["own_sentiment"] or "").lower() in ("negative", "mixed"))]
    L.append("\n## Statements about you to check against the facts\n")
    if claims:
        for r in claims[: a.top * 2]:
            tag = f" WRONG: {r['wrong_claim']}" if r["wrong_claim"] else ""
            sent = f" [{r['own_sentiment']}]" if r["own_sentiment"] else ""
            L.append(f"- {r['engine']} {r['id']}{sent}: \"{r['own_quote'][:220]}\"{tag}")
        L.append("\nThese quotes are excerpts. Read the full answer before calling a claim wrong.")
    else:
        L.append("No factual-looking statements about you found in the quotes.")

    text = "\n".join(L) + "\n"
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
        print(f"evidence -> {a.out}")
    else:
        print(text)
    if a.json:
        json.dump({"lost_prompts": lost_prompts,
                   "source_targets": [{"domain": d, "owner": owner_of[d], "lost_prompts": sorted(dl[d]),
                                       "won_answers_citing": dw[d], "urls": urls[d].most_common(5)} for d in targets],
                   "owned_pages": owned, "claims": claims}, open(a.json, "w"), indent=1, default=list)


if __name__ == "__main__":
    main()
