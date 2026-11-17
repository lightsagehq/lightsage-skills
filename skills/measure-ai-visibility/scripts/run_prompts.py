#!/usr/bin/env python3
"""Run a prompt set N times on AI answer engines and local coding agents; save every answer.

Default is a DRY RUN: it prints how many calls would be made, on which engines and
models, and whose keys or subscription pay for them. Nothing is sent until --yes.

Engines
  openai       OpenAI Responses API + web_search tool      env OPENAI_API_KEY
  anthropic    Anthropic Messages API + web_search tool    env ANTHROPIC_API_KEY
  perplexity   Perplexity Sonar chat completions           env PERPLEXITY_API_KEY
  gemini       Gemini generateContent + google_search      env GEMINI_API_KEY (or GOOGLE_API_KEY)
  claude-code  local `claude -p`, WebSearch/WebFetch only, clean temp dir, no CLAUDE.md/MCP/skills
  codex        local `codex exec`, live web search, temp HOME/CODEX_HOME, no config/apps/plugins

Prompt file: .txt (one prompt per line, # comments) or .csv with columns id,intent,prompt.
Output: JSONL, one record per answer. Re-running with the same --out skips answers already saved.

Examples
  python3 run_prompts.py --prompts prompts.csv --engines openai,claude-code --runs 3 --out runs.jsonl
  python3 run_prompts.py --prompts prompts.csv --engines openai,claude-code --runs 3 --out runs.jsonl --yes
"""
import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

API_ENGINES = {
    "openai": {"env": ["OPENAI_API_KEY"], "model": "gpt-6-astra"},
    "anthropic": {"env": ["ANTHROPIC_API_KEY"], "model": "claude-opus-5-5"},
    "perplexity": {"env": ["PERPLEXITY_API_KEY"], "model": "sonar"},
    "gemini": {"env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"], "model": "gemini-4-hydrogen"},
}
AGENT_ENGINES = {"claude-code": {"bin": "claude"}, "codex": {"bin": "codex"}}
URL_RE = re.compile(r"https?://[^\s<>\"'\)\]\}]+")


def load_prompts(path):
    rows = []
    if path.endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as f:
            for i, r in enumerate(csv.DictReader(f), 1):
                text = (r.get("prompt") or "").strip()
                if text:
                    rows.append({"id": (r.get("id") or f"p{i:02d}").strip(),
                                 "intent": (r.get("intent") or "").strip(), "prompt": text})
    else:
        with open(path, encoding="utf-8") as f:
            n = 0
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    n += 1
                    rows.append({"id": f"p{n:02d}", "intent": "", "prompt": line})
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        sys.exit("error: duplicate prompt ids in " + path)
    return rows


def api_key(engine):
    for name in API_ENGINES[engine]["env"]:
        if os.environ.get(name):
            return name, os.environ[name]
    return API_ENGINES[engine]["env"][0], None


def post_json(url, body, headers, timeout=240, retries=3):
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"content-type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 504, 529) and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"network error: {e}")


def dedupe(items, key="url"):
    seen, out = set(), []
    for it in items:
        k = it.get(key) if isinstance(it, dict) else it
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


def run_openai(prompt, model, key, country):
    tool = {"type": "web_search"}
    if country:
        tool["user_location"] = {"type": "approximate", "country": country}
    body = {"model": model, "input": prompt, "tools": [tool],
            "include": ["web_search_call.action.sources"]}
    r = post_json("https://api.openai.com/v1/responses", body, {"authorization": f"Bearer {key}"})
    text, cites, seen, searched = [], [], [], False
    for item in r.get("output", []):
        if item.get("type") == "web_search_call":
            searched = True
            for s in (item.get("action") or {}).get("sources") or []:
                if s.get("url"):
                    seen.append(s["url"])
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    text.append(c.get("text", ""))
                    for a in c.get("annotations", []):
                        if a.get("type") == "url_citation":
                            cites.append({"url": a.get("url"), "title": a.get("title")})
    return {"answer": "\n".join(text), "citations": dedupe(cites), "sources_seen": dedupe(seen),
            "searched": searched, "model": r.get("model", model)}


def run_anthropic(prompt, model, key, country):
    tool = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}
    if country:
        tool["user_location"] = {"type": "approximate", "country": country}
    headers = {"x-api-key": key, "anthropic-version": "2026-10-21"}
    messages = [{"role": "user", "content": prompt}]
    text, cites, seen, searched, used_model = [], [], [], False, model
    for _ in range(4):  # follow pause_turn continuations
        r = post_json("https://api.anthropic.com/v1/messages",
                      {"model": model, "max_tokens": 16000, "messages": messages, "tools": [tool]}, headers)
        used_model = r.get("model", model)
        if r.get("stop_reason") == "refusal":
            raise RuntimeError("model refused: " + json.dumps(r.get("stop_details")))
        for b in r.get("content", []):
            if b.get("type") == "text":
                text.append(b.get("text", ""))
                for c in b.get("citations") or []:
                    if c.get("url"):
                        cites.append({"url": c["url"], "title": c.get("title")})
            elif b.get("type") == "server_tool_use":
                searched = True
            elif b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
                seen += [x.get("url") for x in b["content"] if x.get("url")]
        if r.get("stop_reason") != "pause_turn":
            break
        messages = messages + [{"role": "assistant", "content": r["content"]}]
    return {"answer": "".join(text), "citations": dedupe(cites), "sources_seen": dedupe(seen),
            "searched": searched, "model": used_model}


def run_perplexity(prompt, model, key, country):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if country:
        body["web_search_options"] = {"user_location": {"country": country}}
    r = post_json("https://api.perplexity.ai/chat/completions", body, {"authorization": f"Bearer {key}"})
    msg = (r.get("choices") or [{}])[0].get("message", {})
    results = r.get("search_results") or []
    titles = {x.get("url"): x.get("title") for x in results}
    cites = [{"url": u, "title": titles.get(u)} for u in (r.get("citations") or [])]
    if not cites:
        cites = [{"url": x.get("url"), "title": x.get("title")} for x in results]
    return {"answer": msg.get("content", ""), "citations": dedupe(cites),
            "sources_seen": dedupe([x.get("url") for x in results]), "searched": bool(results),
            "model": r.get("model", model)}


def run_gemini(prompt, model, key, country):
    body = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = post_json(url, body, {"x-goog-api-key": key})
    cand = (r.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    gm = cand.get("groundingMetadata") or {}
    # Gemini returns redirect URIs; the chunk title holds the real source domain.
    cites = [{"url": c["web"].get("uri"), "title": c["web"].get("title"), "domain": c["web"].get("title")}
             for c in gm.get("groundingChunks", []) if c.get("web")]
    return {"answer": text, "citations": dedupe(cites), "sources_seen": [],
            "searched": bool(gm.get("webSearchQueries")), "model": r.get("modelVersion", model)}


def urls_in(obj):
    s = obj if isinstance(obj, str) else json.dumps(obj)
    return [u.rstrip(".,;:") for u in URL_RE.findall(s)]


def run_claude_code(prompt, model, bin_path, search_hint, timeout):
    work = tempfile.mkdtemp(prefix="vis-cc-")
    env = dict(os.environ, CLAUDE_CODE_DISABLE_CLAUDE_MDS="1")
    cmd = [bin_path, "-p", prompt + (" Use web search." if search_hint else ""),
           "--output-format", "stream-json", "--verbose", "--setting-sources", "",
           "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
           "--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch,WebFetch"]
    if model:
        cmd += ["--model", model]
    try:
        p = subprocess.run(cmd, cwd=work, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=timeout)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    answer, seen, queries, used_model, cost = "", [], [], model, None
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("model"):
            used_model = ev["model"]
        elif t == "assistant":
            for b in (ev.get("message") or {}).get("content", []):
                if b.get("type") == "tool_use":
                    inp = b.get("input") or {}
                    if b.get("name") == "WebSearch":
                        queries.append(inp.get("query"))
                    if b.get("name") == "WebFetch" and inp.get("url"):
                        seen.append(inp["url"])
        elif t == "user":
            for b in (ev.get("message") or {}).get("content", []):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    seen += urls_in(b.get("content"))
        elif t == "result":
            answer = ev.get("result") or ""
            cost = ev.get("total_cost_usd")
            if ev.get("is_error"):
                raise RuntimeError("claude error: " + answer[:300])
    if not answer and p.returncode != 0:
        raise RuntimeError(f"claude exit {p.returncode}: {p.stderr[-400:]}")
    return {"answer": answer, "citations": [{"url": u, "title": None} for u in dedupe(urls_in(answer))],
            "sources_seen": dedupe(seen), "searched": bool(queries or seen), "model": used_model,
            "meta": {"search_queries": queries, "cost_usd_reported": cost}}


def run_codex(prompt, model, bin_path, search_hint, timeout):
    home = tempfile.mkdtemp(prefix="vis-cx-")
    codex_home, work = os.path.join(home, ".codex"), os.path.join(home, "work")
    os.makedirs(codex_home)
    os.makedirs(work)
    real_auth = os.path.join(os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"), "auth.json")
    if os.path.exists(real_auth):
        os.symlink(real_auth, os.path.join(codex_home, "auth.json"))
    env = dict(os.environ, HOME=home, CODEX_HOME=codex_home)
    last = os.path.join(home, "last.txt")
    cmd = [bin_path, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-C", work,
           "-c", 'web_search="live"', "--disable", "apps", "--disable", "plugins", "--disable", "memories",
           "--json", "-o", last]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt + (" Use web search." if search_hint else ""))
    try:
        p = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=timeout)
        answer = open(last, encoding="utf-8").read() if os.path.exists(last) else ""
    finally:
        shutil.rmtree(home, ignore_errors=True)
    queries, used_model = [], model
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        item = ev.get("item") or {}
        if item.get("type") == "web_search" and item.get("query"):
            queries.append(item["query"])
        if ev.get("model"):
            used_model = ev["model"]
    if not answer:
        raise RuntimeError(f"codex exit {p.returncode}: {(p.stderr or p.stdout)[-400:]}")
    return {"answer": answer, "citations": [{"url": u, "title": None} for u in dedupe(urls_in(answer))],
            "sources_seen": [], "searched": bool(dedupe(queries)), "model": used_model or "codex default",
            "meta": {"search_queries": dedupe(queries)}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompts", required=True, help=".txt or .csv (id,intent,prompt)")
    ap.add_argument("--engines", required=True, help="comma list: " + ",".join(list(API_ENGINES) + list(AGENT_ENGINES)))
    ap.add_argument("--runs", type=int, default=3, help="runs per prompt per engine (min 3; default 3)")
    ap.add_argument("--out", required=True, help="JSONL output; existing answers are kept and skipped")
    ap.add_argument("--model", action="append", default=[], metavar="ENGINE=MODEL", help="override a model")
    ap.add_argument("--country", default="US", help="approximate user country for engines that accept it ('' = none)")
    ap.add_argument("--search-hint", action="store_true",
                    help="append 'Use web search.' for coding agents; saved as engine '<agent>-search'")
    ap.add_argument("--workers", type=int, default=3, help="parallel calls (agents count too)")
    ap.add_argument("--timeout", type=int, default=420, help="seconds per agent session")
    ap.add_argument("--claude-bin", default="claude")
    ap.add_argument("--codex-bin", default="codex")
    ap.add_argument("--limit", type=int, default=0, help="only the first N prompts (smoke test)")
    ap.add_argument("--yes", action="store_true", help="actually send the calls (after the user agreed)")
    a = ap.parse_args()

    engines = [e.strip() for e in a.engines.split(",") if e.strip()]
    bad = [e for e in engines if e not in API_ENGINES and e not in AGENT_ENGINES]
    if bad:
        sys.exit(f"error: unknown engine(s) {bad}. Copilot, ChatGPT app, AI Overviews: use paste mode (tally.py import-paste).")
    if a.runs < 3:
        print("warning: fewer than 3 runs per prompt cannot show run-to-run variation", file=sys.stderr)
    models = {}
    for m in a.model:
        k, _, v = m.partition("=")
        models[k.strip()] = v.strip()
    prompts = load_prompts(a.prompts)
    if a.limit:
        prompts = prompts[: a.limit]

    done = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not r.get("error"):
                    done.add((r["prompt_id"], r["engine"], r["run"]))

    def label(e):  # the search-hint arm is a separate engine in the results
        return e + "-search" if a.search_hint and e in AGENT_ENGINES else e

    plan, usable = [], []
    print(f"Plan: {len(prompts)} prompts x {a.runs} runs on {len(engines)} engine(s)")
    for e in engines:
        todo = [(p, e, i) for p in prompts for i in range(1, a.runs + 1) if (p["id"], label(e), i) not in done]
        if e in API_ENGINES:
            name, key = api_key(e)
            model = models.get(e, API_ENGINES[e]["model"])
            state = "set" if key else "NOT SET, engine skipped"
            print(f"  {e:<11} model {model}, web search on: {len(todo)} API calls billed to YOUR key in {name} [{state}]")
            if key:
                usable.append(e)
                plan += todo
        else:
            b = a.claude_bin if e == "claude-code" else a.codex_bin
            found = shutil.which(b)
            model = models.get(e, "agent default")
            state = "found" if found else "NOT FOUND, engine skipped"
            print(f"  {e:<11} model {model}: {len(todo)} local agent sessions on YOUR subscription/login [{b}: {state}]")
            if found:
                usable.append(e)
                plan += todo
    skipped = sum(1 for p in prompts for e in engines for i in range(1, a.runs + 1) if (p["id"], label(e), i) in done)
    if skipped:
        print(f"  {skipped} answers already in {a.out} will be skipped")
    print(f"Total to send: {len(plan)}. Web search usually adds a per-search fee on API engines.")
    if not plan:
        sys.exit(0 if skipped else 2)
    if not a.yes:
        print("DRY RUN: nothing was sent. Show this plan to the user; re-run with --yes only after they agree.")
        return

    lock = threading.Lock()
    out = open(a.out, "a", encoding="utf-8")
    counts = {"ok": 0, "error": 0}

    def work(job):
        p, e, i = job
        t0 = time.time()
        rec = {"prompt_id": p["id"], "intent": p["intent"], "prompt": p["prompt"], "engine": label(e), "run": i,
               "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "country": a.country or None, "answer": "", "citations": [], "sources_seen": [],
               "searched": None, "model": None, "error": None, "meta": {}}
        try:
            if e in API_ENGINES:
                fn = {"openai": run_openai, "anthropic": run_anthropic,
                      "perplexity": run_perplexity, "gemini": run_gemini}[e]
                res = fn(p["prompt"], models.get(e, API_ENGINES[e]["model"]), api_key(e)[1], a.country)
            elif e == "claude-code":
                res = run_claude_code(p["prompt"], models.get(e), a.claude_bin, a.search_hint, a.timeout)
            else:
                res = run_codex(p["prompt"], models.get(e), a.codex_bin, a.search_hint, a.timeout)
            meta = res.pop("meta", {})
            rec.update(res)
            rec["meta"].update(meta)
        except Exception as ex:  # keep going; the record carries the error
            rec["error"] = str(ex)[:600]
        rec["meta"]["latency_s"] = round(time.time() - t0, 1)
        with lock:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            counts["error" if rec["error"] else "ok"] += 1
            n = counts["ok"] + counts["error"]
            flag = "ERROR " + rec["error"][:120] if rec["error"] else f"{len(rec['answer'])} chars"
            print(f"[{n}/{len(plan)}] {label(e)} {p['id']} run {i}: {flag}", file=sys.stderr)

    with cf.ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        list(ex.map(work, plan))
    out.close()
    print(f"Done: {counts['ok']} answers, {counts['error']} errors -> {a.out}")
    if counts["error"]:
        print("Errored calls are not counted as answers. Re-run the same command to retry them.")


if __name__ == "__main__":
    main()
