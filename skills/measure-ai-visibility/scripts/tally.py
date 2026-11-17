#!/usr/bin/env python3
"""Extract mentions, citations and competitors from saved AI answers, then report rates with n and ranges.

Subcommands
  import-paste  answers.txt -> runs.jsonl   (answers the user copied from ChatGPT, Copilot, AI Overviews...)
  extract       runs.jsonl + brands.json -> extracted.jsonl   (deterministic: names, order, citations)
  labels        extracted.jsonl -> labels.jsonl template, one line per answer that names your brand,
                for a reader (you, the agent) to fill: recommended true/false, sentiment, wrong_claim
  report        extracted.jsonl [--labels labels.jsonl] -> markdown report (+ --json summary)

Paste format (one block per answer; Sources lines optional, URLs anywhere are kept):
  === engine: chatgpt-app | run: 1 | prompt: best email api for a small saas
  <answer text>

brands.json:
  {"brand": {"name": "Acme", "aliases": ["Acme Mail"], "domains": ["acme.com"]},
   "competitors": [{"name": "Postbird", "aliases": [], "domains": ["postbird.io"]}],
   "case_sensitive": ["Acme"]}      # names that are also common words: match exact case only
"""
import argparse
import collections
import csv
import json
import random
import re
import sys
import urllib.parse

URL_RE = re.compile(r"https?://[^\s<>\"'\)\]\}]+")
LIST_NAME_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+\**\[?([A-Z][\w.&+'-]*(?:\s[A-Z][\w.&+'-]*){0,2})", re.M)
BOLD_NAME_RE = re.compile(r"\*\*\[?([A-Z][\w.&+'-]*(?:\s[A-Z][\w.&+'-]*){0,2})\]?")
BARE_DOMAIN_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})(?:/[^\s,;]*)?", re.I)
STOP = {"The", "This", "These", "Best", "Pros", "Cons", "Note", "Why", "When", "What", "How", "If", "For",
        "Use", "Pick", "Option", "Summary", "Bottom", "Recommendation", "Pricing", "Free", "Yes", "No",
        "Sources", "Source", "Tool", "Best For", "Main", "My", "Quick", "Choose", "Top", "Step", "Example"}


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def domain_of(url):
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def owns(domain, domains):
    return any(domain == d or domain.endswith("." + d) for d in domains)


# ---------- import-paste ----------
def cmd_import_paste(a):
    text = open(a.file, encoding="utf-8").read()
    prompts = {}
    if a.prompts:
        with open(a.prompts, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                prompts[r["prompt"].strip().lower()] = r
                prompts[r["id"].strip().lower()] = r
    blocks = re.split(r"^===[ \t]*", text, flags=re.M)[1:]
    rows, auto = [], {}
    for b in blocks:
        header, _, body = b.partition("\n")
        meta = {}
        for part in header.split("|"):
            k, _, v = part.partition(":")
            meta[k.strip().lower()] = v.strip()
        ptext = meta.get("prompt", "")
        ref = prompts.get(ptext.lower()) or prompts.get(meta.get("id", "").lower())
        pid = ref["id"] if ref else meta.get("id") or auto.setdefault(ptext.lower(), f"p{len(auto) + 1:02d}")
        found = [u.rstrip(".,;:") for u in URL_RE.findall(body)]
        for line in body.splitlines():  # "Sources: g2.com, example.org" with no scheme
            if re.match(r"\s*sources?\s*:", line, re.I):
                found += ["https://" + d for d in BARE_DOMAIN_RE.findall(URL_RE.sub(" ", line.split(":", 1)[1]))]
        urls = list(dict.fromkeys(found))
        rows.append({"prompt_id": pid, "intent": (ref or {}).get("intent", meta.get("intent", "")),
                     "prompt": (ref or {}).get("prompt", ptext), "engine": meta.get("engine", "unknown"),
                     "run": int(meta.get("run", "1") or 1), "ts": meta.get("date"), "country": meta.get("country"),
                     "answer": body.strip(), "citations": [{"url": u, "title": None} for u in urls],
                     "sources_seen": [], "searched": None, "model": meta.get("model", "consumer app"),
                     "error": None, "meta": {"source": "paste", "logged_in": meta.get("logged_in")}})
    write_jsonl(a.out, rows)
    print(f"{len(rows)} pasted answers -> {a.out}")


# ---------- extract ----------
def compile_brand(b, case_sensitive):
    names = [b["name"]] + list(b.get("aliases", []))
    pats = []
    for n in names:
        flags = 0 if n in case_sensitive else re.I
        pats.append(re.compile(r"(?<![\w.-])" + re.escape(n) + r"(?![\w-])", flags))
    for d in b.get("domains", []):
        pats.append(re.compile(re.escape(d), re.I))
    return pats


def first_hit(text, pats):
    best = None
    for p in pats:
        m = p.search(text)
        if m and (best is None or m.start() < best):
            best = m.start()
    return best


def sentence_at(text, pos, width=280):
    start = max(text.rfind("\n", 0, pos), text.rfind(". ", 0, pos)) + 1
    end_candidates = [i for i in (text.find("\n", pos), text.find(". ", pos)) if i != -1]
    end = min(end_candidates) + 1 if end_candidates else len(text)
    return text[start:end].strip()[:width]


def cmd_extract(a):
    cfg = json.load(open(a.brands, encoding="utf-8"))
    cs = set(cfg.get("case_sensitive", []))
    brand = cfg["brand"]
    tracked = [brand] + cfg.get("competitors", [])
    pats = {b["name"]: compile_brand(b, cs) for b in tracked}
    owned = [d.lower() for d in brand.get("domains", [])]
    comp_domains = {b["name"]: [d.lower() for d in b.get("domains", [])] for b in cfg.get("competitors", [])}

    latest = {}
    for r in read_jsonl(a.runs):
        k = (r["prompt_id"], r["engine"], r["run"])
        if r.get("error") and k in latest and not latest[k].get("error"):
            continue
        latest[k] = r
    out, errors = [], 0
    for r in latest.values():
        if r.get("error"):
            errors += 1
            continue
        text = r.get("answer") or ""
        hits = {n: first_hit(text, p) for n, p in pats.items()}
        named = sorted((pos, n) for n, pos in hits.items() if pos is not None)
        # Brands the prompt itself names ("alternatives to X") are left out of the order.
        in_prompt = {n for n, p in pats.items() if first_hit(r.get("prompt") or "", p) is not None}
        ranked = [n for _, n in named if n not in in_prompt]
        order = {n: (ranked.index(n) + 1 if n in ranked else None) for _, n in named}
        mentions = [{"brand": n, "is_own": n == brand["name"], "order": order[n], "in_prompt": n in in_prompt,
                     "is_first": order[n] == 1, "quote": sentence_at(text, pos)} for pos, n in named]
        cites = []
        for c in r.get("citations") or []:
            d = (c.get("domain") or domain_of(c.get("url", ""))).lower().removeprefix("www.")
            owner = "own" if owns(d, owned) else next(
                (n for n, ds in comp_domains.items() if owns(d, ds)), "third-party")
            cites.append({"url": c.get("url"), "domain": d, "owner": owner, "is_company_link": owner == "own"})
        cands = collections.Counter()
        known = {x.lower() for b in tracked for x in [b["name"]] + b.get("aliases", [])}
        for m in LIST_NAME_RE.findall(text) + BOLD_NAME_RE.findall(text):
            m = m.strip()
            if m and m not in STOP and m.lower() not in known and len(m) > 2:
                cands[m] += 1
        own = hits[brand["name"]] is not None
        out.append({**{k: r.get(k) for k in ("prompt_id", "intent", "prompt", "engine", "run", "ts", "model",
                                              "country", "searched")},
                    "answer": text, "brand": brand["name"], "brand_mentioned": own,
                    "brand_status": ("first" if own and order[brand["name"]] == 1 else "among" if own else "not"),
                    "brand_cited": any(c["owner"] == "own" for c in cites),
                    "competitors_mentioned": [n for _, n in named if n != brand["name"]],
                    "mentions": mentions, "citations": cites, "untracked_names": sorted(cands)})
    write_jsonl(a.out, out)
    print(f"{len(out)} answers extracted -> {a.out} ({errors} errored calls ignored)")


# ---------- labels ----------
def rkey(r):
    return f"{r['prompt_id']}|{r['engine']}|{r['run']}"


def cmd_labels(a):
    rows = []
    for r in read_jsonl(a.extracted):
        own = next((m for m in r["mentions"] if m["is_own"]), None)
        if own and (r.get("intent") or "").lower() != "control":
            rows.append({"key": rkey(r), "prompt": r["prompt"], "engine": r["engine"], "quote": own["quote"],
                         "recommended": None, "sentiment": None, "wrong_claim": None})
    write_jsonl(a.out, rows)
    print(f"{len(rows)} answers name the brand -> {a.out}. Read each answer (not only the quote) and fill "
          "recommended (true/false), sentiment (positive/neutral/negative/mixed), wrong_claim (text or null).")


# ---------- report ----------
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (max(0.0, c - h), min(1.0, c + h))


def cluster_ci(clusters, iters=2000, seed=7):
    """95% bootstrap interval for k/n resampling whole prompts (runs of one prompt are correlated)."""
    if not clusters:
        return (0.0, 0.0)
    rng = random.Random(seed)
    stats = []
    for _ in range(iters):
        s = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        n = sum(x[1] for x in s)
        stats.append(sum(x[0] for x in s) / n if n else 0)
    stats.sort()
    return (stats[int(0.025 * iters)], stats[int(0.975 * iters) - 1])


def pct(x):
    return f"{100 * x:.0f}%"


def rate_cell(k, n, clusters):
    if len(clusters) < 5:
        return f"{k}/{n} = {pct(k / n) if n else '-'} (under 5 prompts: no range)"
    lo, hi = cluster_ci(clusters)
    return f"{k}/{n} = {pct(k / n) if n else '-'} ({pct(lo)}–{pct(hi)})"


def cmd_report(a):
    rows = read_jsonl(a.extracted)
    labels = {l["key"]: l for l in read_jsonl(a.labels)} if a.labels else {}
    controls = [r for r in rows if (r.get("intent") or "").lower() == "control"]
    rows = [r for r in rows if (r.get("intent") or "").lower() != "control"]
    if not rows:
        sys.exit("no non-control answers to report")
    engines = sorted({r["engine"] for r in rows})
    by_ep = collections.defaultdict(list)
    for r in rows:
        by_ep[(r["engine"], r["prompt_id"])].append(r)
    seen_comps = {c for r in rows for c in r["competitors_mentioned"]}
    if a.brands:
        seen_comps |= {c["name"] for c in json.load(open(a.brands, encoding="utf-8")).get("competitors", [])}
    comps = sorted(seen_comps)
    summary = {"engines": {}, "gaps": [], "domains": [], "unstable": []}
    L = []
    prompts = sorted({r["prompt_id"] for r in rows})
    runs_per = [len(v) for v in by_ep.values()]
    dates = sorted(r["ts"][:10] for r in rows if r.get("ts"))
    L.append("# AI visibility report\n")
    L.append(f"Sample: {len(prompts)} prompts, {len(engines)} engine(s), {len(rows)} answers, "
             f"{min(runs_per)}–{max(runs_per)} runs per prompt per engine"
             + (f", {dates[0]} to {dates[-1]}" if dates else "") + ". Control prompts excluded from rates.\n")
    L.append("Rates are answers that did X / answers. The range is a 95% interval that resamples whole prompts, "
             "so it stays honest when runs of one prompt agree with each other.\n")

    L.append("## Per engine\n")
    L.append("| Engine | Model | Answers | Searched the web | Brand named | Named first (of tracked) | Own site cited | Prompts where named in ≥1 run | in most runs |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for e in engines:
        er = [r for r in rows if r["engine"] == e]
        cl = lambda f: [(sum(1 for r in v if f(r)), len(v)) for (ee, _), v in by_ep.items() if ee == e]
        n = len(er)
        k_m = sum(r["brand_mentioned"] for r in er)
        k_f = sum(r["brand_status"] == "first" for r in er)
        k_c = sum(r["brand_cited"] for r in er)
        srch = [r["searched"] for r in er if r.get("searched") is not None]
        eps = [v for (ee, _), v in by_ep.items() if ee == e]
        any_p = sum(1 for v in eps if any(r["brand_mentioned"] for r in v))
        maj_p = sum(1 for v in eps if sum(r["brand_mentioned"] for r in v) * 2 > len(v))
        lo, hi = wilson(any_p, len(eps))
        models = ", ".join(sorted({str(r.get("model")) for r in er}))
        L.append(f"| {e} | {models} | {n} | {f'{sum(srch)}/{len(srch)}' if srch else 'unknown'} | "
                 f"{rate_cell(k_m, n, cl(lambda r: r['brand_mentioned']))} | "
                 f"{rate_cell(k_f, n, cl(lambda r: r['brand_status'] == 'first'))} | "
                 f"{rate_cell(k_c, n, cl(lambda r: r['brand_cited']))} | "
                 f"{any_p}/{len(eps)} ({pct(lo)}–{pct(hi)}) | {maj_p}/{len(eps)} |")
        summary["engines"][e] = {"answers": n, "brand_mentioned": k_m, "brand_first": k_f, "brand_cited": k_c,
                                 "prompts": len(eps), "prompts_any": any_p, "prompts_majority": maj_p}
        lab = [labels[rkey(r)] for r in er if rkey(r) in labels and labels[rkey(r)].get("recommended") is not None]
        if lab:
            summary["engines"][e]["recommended_labelled"] = [sum(1 for l in lab if l["recommended"]), len(lab)]

    if comps:
        L.append("\n## Who shows up (share of answers naming each brand)\n")
        L.append("| Brand | " + " | ".join(engines) + " |")
        L.append("|---|" + "---|" * len(engines))
        brand_name = rows[0].get("brand") or "Your brand"
        for name in [brand_name] + comps:
            cells = []
            for e in engines:
                er = [r for r in rows if r["engine"] == e]
                k = sum(1 for r in er if any(m["brand"] == name for m in r["mentions"]))
                cells.append(f"{k}/{len(er)} = {pct(k / len(er))}")
            L.append(f"| {name} | " + " | ".join(cells) + " |")

    L.append("\n## Gap prompts: a competitor in most runs, your brand in none\n")
    gaps = []
    for (e, pid), v in sorted(by_ep.items()):
        if any(r["brand_mentioned"] for r in v):
            continue
        cc = collections.Counter(c for r in v for c in r["competitors_mentioned"])
        winners = [(c, k) for c, k in cc.most_common() if k * 2 >= len(v)]
        if winners:
            doms = collections.Counter(c["domain"] for r in v for c in r["citations"])
            gaps.append({"engine": e, "prompt_id": pid, "prompt": v[0]["prompt"], "runs": len(v),
                         "competitors": winners, "cited": doms.most_common(5)})
    if gaps:
        L.append("| Engine | Prompt | Competitors (runs) | Most cited there |")
        L.append("|---|---|---|---|")
        for g in gaps:
            L.append(f"| {g['engine']} | {g['prompt_id']}: {g['prompt'][:80]} | "
                     + ", ".join(f"{c} {k}/{g['runs']}" for c, k in g["competitors"]) + " | "
                     + ", ".join(f"{d} ({k})" for d, k in g["cited"]) + " |")
    else:
        L.append("None found.")
    summary["gaps"] = gaps

    unstable = [(e, pid, sum(r["brand_mentioned"] for r in v), len(v)) for (e, pid), v in sorted(by_ep.items())
                if 0 < sum(r["brand_mentioned"] for r in v) < len(v)]
    L.append("\n## Unstable prompts: named in some runs, not others\n")
    L.append("\n".join(f"- {e} {pid}: {k}/{n} runs" for e, pid, k, n in unstable) or "None.")
    L.append("These are where more runs or a small content change can move the number; one run would have shown either answer.")
    summary["unstable"] = unstable

    L.append("\n## Most cited domains (answers citing each, any engine)\n")
    dom = collections.defaultdict(lambda: {"answers": 0, "engines": set(), "owner": "", "in_gaps": 0})
    gap_keys = {(g["engine"], g["prompt_id"]) for g in gaps}
    for r in rows:
        for d in {c["domain"]: c["owner"] for c in r["citations"]}.items():
            x = dom[d[0]]
            x["answers"] += 1
            x["engines"].add(r["engine"])
            x["owner"] = d[1]
            x["in_gaps"] += (r["engine"], r["prompt_id"]) in gap_keys
    top = sorted(dom.items(), key=lambda kv: (-kv[1]["answers"], kv[0]))[: a.top]
    cited_answers = sum(1 for r in rows if r["citations"])
    L.append(f"{cited_answers}/{len(rows)} answers carried at least one citation.\n")
    if top:
        L.append("| Domain | Owner | Answers | In gap-prompt answers | Engines |")
        L.append("|---|---|---|---|---|")
        for d, x in top:
            L.append(f"| {d} | {x['owner']} | {x['answers']} | {x['in_gaps']} | {', '.join(sorted(x['engines']))} |")
    summary["domains"] = [{"domain": d, **{k: (sorted(v) if isinstance(v, set) else v) for k, v in x.items()}}
                          for d, x in top]

    unt = collections.Counter(n for r in rows for n in r["untracked_names"])
    common = [(n, k) for n, k in unt.most_common(15) if k >= 2]
    if common:
        L.append("\n## Names in list items or bold that are not in brands.json (check: competitor or noise?)\n")
        L.append(", ".join(f"{n} ({k})" for n, k in common))

    if labels:
        lab = [l for l in labels.values() if l.get("recommended") is not None]
        sent = collections.Counter(l.get("sentiment") for l in labels.values() if l.get("sentiment"))
        wrong = [l for l in labels.values() if l.get("wrong_claim")]
        L.append("\n## Read by hand (labels)\n")
        for e in sorted({l["engine"] for l in lab}):
            el = [l for l in lab if l["engine"] == e]
            L.append(f"- {e}: recommended in {sum(1 for l in el if l['recommended'])}/{len(el)} answers that name you")
        L.append(f"- Sentiment: " + (", ".join(f"{s} {k}" for s, k in sent.most_common()) or "not labelled"))
        for l in wrong[:10]:
            L.append(f"- Wrong claim ({l['engine']}, {l['key']}): {l['wrong_claim']}")

    if controls:
        L.append("\n## Control prompts (should always name you; if not, the extraction or the engine is off)\n")
        for r in controls:
            L.append(f"- {r['engine']} {r['prompt_id']} run {r['run']}: {'named' if r['brand_mentioned'] else 'NOT named'}")

    L.append("\n## Limits of this measurement\n")
    small = [e for e, s in summary["engines"].items() if s["answers"] < 30]
    if small:
        L.append(f"- Under 30 answers on {', '.join(small)}: ranges are wide; do not compare small differences.")
    L.append("- API and coding-agent answers are not the consumer apps: no login, memory, personalization or app-side search settings.")
    L.append("- Answers change with model version, date, country and wording; compare only runs with the same prompts, engines and settings.")
    L.append("- 'Named first' is the order among brands in brands.json, not a judged recommendation; use labels for that.")
    text = "\n".join(L) + "\n"
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
        print(f"report -> {a.out}")
    else:
        print(text)
    if a.json:
        json.dump(summary, open(a.json, "w"), indent=1, default=list)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import-paste", help="pasted answers -> runs.jsonl")
    p.add_argument("file")
    p.add_argument("--prompts", help="prompts.csv to match prompt text or id")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_import_paste)
    p = sub.add_parser("extract", help="runs.jsonl -> extracted.jsonl")
    p.add_argument("runs")
    p.add_argument("--brands", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_extract)
    p = sub.add_parser("labels", help="template for hand labels")
    p.add_argument("extracted")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_labels)
    p = sub.add_parser("report", help="markdown report")
    p.add_argument("extracted")
    p.add_argument("--brands", help="brands.json, to list competitors that never appeared")
    p.add_argument("--labels")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--out")
    p.add_argument("--json", help="also write a JSON summary")
    p.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
