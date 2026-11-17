#!/usr/bin/env python3
"""Classify AI agents and bots in web server or CDN logs and write a markdown report.

Input formats (auto-detected per file; .gz is fine):
  combined   nginx / Apache combined or common log format (optionally vhost-prefixed)
  json       JSON lines or a JSON array: Vercel log drains / CLI exports, Cloudflare
             Logpush, Netlify log drains, or any JSON with user agent / path / status fields
  cf-graphql Cloudflare GraphQL export (httpRequestsAdaptiveGroups with count + dimensions)
  w3c        AWS CloudFront standard logs, IIS and other W3C extended logs (#Fields: header)
  csv        any CSV with a header row (user agent, path or URL, status, time, ...)
Unknown column names: pass --map ua=Agent,path=Uri,status=Code,time=When,referer=Ref,ip=Client,host=Site

Classes: coding-agent, ai-user-fetch, ai-search, ai-training, other-bot, human.
User agents are claims. --verify-ips checks AI and search bot IPs against the
providers' published IP lists (downloads ~10 small JSON files).

Examples:
  python3 analyze_logs.py access.log.gz
  python3 analyze_logs.py vercel-logs.json --site docs.example.com --out report.md
  python3 analyze_logs.py export.csv --map ua=UserAgent,path=RequestPath --json summary.json
  python3 analyze_logs.py fixtures/combined.log --verify-ips
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import gzip
import io
import ipaddress
import json
import re
import sys
import urllib.parse
import urllib.request

CLASSES = ["coding-agent", "ai-user-fetch", "ai-search", "ai-training", "other-bot", "human"]
CLASS_LABEL = {
    "coding-agent": "Coding agents",
    "ai-user-fetch": "AI fetches for a user",
    "ai-search": "AI search crawlers",
    "ai-training": "AI training crawlers",
    "other-bot": "Other bots and scripts",
    "human": "People (browsers)",
}

# ------------------------------------------------------------------ classification
# Substring (lowercase) -> agent name. Order matters: specific before general.
CODING_AGENT_TOKENS = [
    ("claude-code", "Claude Code"),
    ("githubcopilotruntime", "GitHub Copilot"),
    ("openclaw", "OpenClaw"),
    ("codex", "Codex"),
    ("opencode", "OpenCode"),
    ("trae/", "Trae"),
    ("kiro-cli", "Kiro"), ("kiro/", "Kiro"),
    ("augment.cli/", "Augment"), ("augment-webfetch", "Augment"),
    ("devin/", "Devin"),
    ("aider/", "Aider"),
    ("qwencode/", "Qwen Code"),
    ("cline.bot", "Cline"),
    ("google-gemini-cli", "Gemini CLI"),
    ("googleagent-urlcontext", "Gemini URL context"),
    ("modelcontextprotocol/", "MCP fetch server"),
    ("exauser", "Exa (fetching for an agent)"),
    ("qodercli", "Qoder"),
    ("zcode-webfetch", "Z Code"),
]
CODING_AGENT_PREFIXES = [("zed/", "Zed"), ("crush/", "Crush"), ("goose/", "Goose")]
VSCODE_ELECTRON = re.compile(r"\bcode/\d[^ ]* .*electron/\d", re.I)

# AI provider bots: token -> (name, class)
AI_BOTS = [
    # user-triggered fetches
    ("chatgpt-user", "ChatGPT-User", "ai-user-fetch"),
    ("oai-operator", "OAI-Operator (ChatGPT agent)", "ai-user-fetch"),
    ("claude-user", "Claude-User", "ai-user-fetch"),
    ("perplexity-user", "Perplexity-User", "ai-user-fetch"),
    ("mistralai-user", "MistralAI-User", "ai-user-fetch"),
    ("meta-externalfetcher", "meta-externalfetcher", "ai-user-fetch"),
    ("agent.meta.ai", "Meta AI", "ai-user-fetch"),
    ("gemini-deep-research", "Gemini-Deep-Research", "ai-user-fetch"),
    ("google-notebooklm", "Google-NotebookLM", "ai-user-fetch"),
    ("googleagent-mariner", "GoogleAgent-Mariner", "ai-user-fetch"),
    ("google-agent", "Google-Agent", "ai-user-fetch"),
    ("google-cloudvertexbot", "Google-CloudVertexBot", "ai-user-fetch"),
    ("amazon-user", "Amazon-User", "ai-user-fetch"),
    ("amazonbuyforme", "AmazonBuyForMe", "ai-user-fetch"),
    ("grok-agent", "Grok-Agent", "ai-user-fetch"),
    ("microsoftpreview", "MicrosoftPreview", "ai-user-fetch"),
    ("deepseekbot", "DeepSeekBot", "ai-user-fetch"),
    ("cohere-ai", "cohere-ai", "ai-user-fetch"),
    ("kimi-searchbot", "Kimi", "ai-user-fetch"),
    # AI search indexers
    ("oai-searchbot", "OAI-SearchBot", "ai-search"),
    ("claude-searchbot", "Claude-SearchBot", "ai-search"),
    ("perplexitybot", "PerplexityBot", "ai-search"),
    ("youbot", "YouBot", "ai-search"),
    ("azureai-searchbot", "AzureAI-SearchBot", "ai-search"),
    ("duckassistbot", "DuckAssistBot", "ai-search"),
    ("meta-webindexer", "meta-webindexer", "ai-search"),
    ("xai-searchbot", "xAI-SearchBot", "ai-search"),
    ("exasearchbot", "Exa crawler", "ai-search"), ("exabot", "Exa crawler", "ai-search"),
    ("linkupbot", "Linkup crawler", "ai-search"),
    # training crawlers
    ("gptbot", "GPTBot", "ai-training"),
    ("claudebot", "ClaudeBot", "ai-training"),
    ("anthropic-ai", "anthropic-ai", "ai-training"),
    ("ccbot", "CCBot", "ai-training"),
    ("bytespider", "Bytespider", "ai-training"),
    ("meta-externalagent", "meta-externalagent", "ai-training"),
    ("cohere-training-data-crawler", "Cohere training crawler", "ai-training"),
    ("ai2bot", "AI2Bot", "ai-training"),
    ("moonshotbot", "Moonshot crawler (purpose undocumented)", "ai-training"),
    ("kimibot", "Moonshot crawler (purpose undocumented)", "ai-training"),
    ("qwenbot", "Qwen crawler (purpose undocumented)", "ai-training"),
]

OTHER_BOTS = [
    ("googlebot", "Googlebot"), ("googleother", "GoogleOther"), ("adsbot-google", "AdsBot-Google"),
    ("bingbot", "Bingbot"), ("applebot", "Applebot"), ("amazonbot", "Amazonbot"),
    ("duckduckbot", "DuckDuckBot"), ("yandex", "Yandex"), ("baiduspider", "Baiduspider"),
    ("petalbot", "PetalBot"), ("bravebot", "Bravebot"), ("seznambot", "SeznamBot"),
    ("ahrefs", "Ahrefs"), ("semrush", "Semrush"), ("mj12bot", "Majestic"), ("dotbot", "Moz"),
    ("screaming frog", "Screaming Frog"), ("dataforseobot", "DataForSEO"),
    ("slackbot", "Slackbot"), ("twitterbot", "Twitterbot"), ("linkedinbot", "LinkedInBot"),
    ("discordbot", "Discordbot"), ("facebookexternalhit", "Facebook preview"), ("whatsapp", "WhatsApp"),
    ("telegrambot", "TelegramBot"), ("redditbot", "Redditbot"),
    ("headlesschrome", "HeadlessChrome"), ("pingdom", "Pingdom"), ("uptime", "uptime monitor"),
    ("datadog", "Datadog"), ("monitor", "monitor"), ("scanner", "scanner"),
]
CLI_CLIENTS = ("curl/", "wget/", "python-requests/", "python-httpx/", "python-urllib/", "aiohttp/",
               "axios/", "node-fetch", "node", "undici", "bun/", "deno/", "go-http-client/",
               "httpie/", "libcurl", "colly", "got (")
DOCS_PREFIXES = ("/docs", "/doc", "/api-reference", "/reference", "/guides", "/guide", "/quickstart", "/sdk", "/sdks")
DOCS_SUFFIXES = (".md", ".mdx", "/llms.txt", "/llms-full.txt")
GENERIC_BOT = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*(?:bot|crawler|spider|scraper)(?![A-Za-z])", re.I)
BROWSER_ENGINES = ("applewebkit", "gecko", "trident", "msie")
SCANNER_PATHS = ("/.env", "/wp-login.php", "/wp-admin", "/xmlrpc.php", "/.git/", "/phpmyadmin", "/actuator",
                 "/cgi-bin/", "/vendor/phpunit", "/.aws/", "/config.json", "/server-status", "/.ds_store")

AI_REFERRERS = [
    ("chatgpt.com", "ChatGPT"), ("chat.openai.com", "ChatGPT"), ("openai.com", "ChatGPT"),
    ("perplexity.ai", "Perplexity"), ("claude.ai", "Claude"), ("gemini.google.com", "Gemini"),
    ("bard.google.com", "Gemini"), ("copilot.microsoft.com", "Microsoft Copilot"),
    ("meta.ai", "Meta AI"), ("grok.com", "Grok"), ("chat.deepseek.com", "DeepSeek"), ("deepseek.com", "DeepSeek"),
    ("chat.mistral.ai", "Mistral"), ("poe.com", "Poe"), ("phind.com", "Phind"), ("you.com", "You.com"),
    ("kagi.com", "Kagi Assistant"),
]
UTM_AI = {"chatgpt.com": "ChatGPT", "chatgpt": "ChatGPT", "openai": "ChatGPT", "perplexity": "Perplexity",
          "perplexity.ai": "Perplexity", "claude.ai": "Claude", "claude": "Claude", "gemini": "Gemini",
          "copilot.com": "Microsoft Copilot", "copilot": "Microsoft Copilot"}


def is_docs(path: str, host: str = "") -> bool:
    p = path.split("?")[0].lower().rstrip("/") or "/"
    if host.lower().startswith(("docs.", "developer.", "developers.")):
        return True
    return p.endswith(DOCS_SUFFIXES) or any(p == x or p.startswith(x + "/") for x in DOCS_PREFIXES)


def classify(ua: str, path: str, host: str = "", accept: str = "") -> tuple[str, str, str]:
    """Return (class, agent name, evidence)."""
    raw = (ua or "").strip()
    u = raw.lower()
    if not u or u == "-":
        return "other-bot", "(empty user agent)", "ua:empty"
    for token, name in CODING_AGENT_TOKENS:
        if token in u:
            return "coding-agent", name, f"ua:{token}"
    for prefix, name in CODING_AGENT_PREFIXES:
        if u.startswith(prefix):
            return "coding-agent", name, f"ua:{prefix}"
    if u == "kilo":
        return "coding-agent", "Kilo Code", "ua:kilo"
    if VSCODE_ELECTRON.search(u):
        return "coding-agent", "VS Code agent fetch", "ua:vscode-electron"
    if u == "mozilla/5.0 (compatible; agentbot/1.0)":
        return "coding-agent", "Cline (inferred)", "ua:agentbot"
    for token, name, cls in AI_BOTS:
        if token in u:
            return cls, name, f"ua:{token}"
    cli = next((c for c in CLI_CLIENTS if u.startswith(c)), None)
    if accept and "text/markdown" in accept.lower() and not any(t in u for t, _ in OTHER_BOTS):
        if accept.strip().lower() == "text/markdown, text/html, */*":
            return "coding-agent", "Claude Code (inferred)", "accept:claude-code"
        return "coding-agent", "unnamed coding agent", "accept:text/markdown"
    if cli and is_docs(path, host):
        return "coding-agent", f"unnamed coding agent ({cli.strip(' (/')})", f"cli-on-docs:{cli.strip(' (/')}"
    for token, name in OTHER_BOTS:
        if token in u:
            return "other-bot", name, f"ua:{token}"
    if cli:
        return "other-bot", cli.strip(" (/"), f"cli:{cli.strip(' (/')}"
    m = GENERIC_BOT.search(re.sub(r"\+?https?://\S+|\S+@\S+", " ", raw))
    if m and m.group(0).lower() != "robot":
        return "other-bot", m.group(0)[:50], "ua:generic-bot"
    if not (u.startswith("mozilla/") and any(e in u for e in BROWSER_ENGINES)):
        name = re.match(r"\s*([A-Za-z][\w.-]*)", raw)
        return "other-bot", (name.group(1) if name else "script")[:50], "ua:non-browser"
    return "human", "browser", "ua:browser"


def ai_referral(referer: str, path: str) -> str | None:
    if referer and referer != "-":
        host = urllib.parse.urlsplit(referer if "://" in referer else "https://" + referer).netloc.lower()
        host = host.split(":")[0].removeprefix("www.")
        for dom, name in AI_REFERRERS:
            if host == dom or host.endswith("." + dom):
                return name
    q = urllib.parse.urlsplit(path).query
    if q:
        for k, v in urllib.parse.parse_qsl(q):
            if k.lower() == "utm_source" and v.lower() in UTM_AI:
                return UTM_AI[v.lower()]
    return None


# ------------------------------------------------------------------ parsing

COMBINED = re.compile(
    r'^(?:(?P<vhost>[^\s]+)\s+(?=\S+\s+\S+\s+\S+\s+\[))?(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+|-)\s*(?P<target>[^"\s]*)[^"]*"\s+(?P<status>\d{3}|-)\s+(?P<bytes>\S+)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<ua>[^"]*)")?')

ALIASES = {
    "ua": ["user_agent", "useragent", "http_user_agent", "clientrequestuseragent", "requestuseragent",
           "ua", "agent", "useragentstring", "csuseragent", "httpuseragent"],
    "path": ["path", "requestpath", "clientrequestpath", "request_path", "uri", "request_uri", "requesturi",
             "clientrequesturi", "url", "requesturl", "pathname", "csuristem", "target", "request"],
    "host": ["host", "hostname", "clientrequesthost", "clientrequesthttphost", "domain", "http_host", "requesthost", "cshost"],
    "status": ["scstatus", "status", "statuscode", "status_code", "edgeresponsestatus", "responsestatuscode", "response_status",
               "originresponsestatus", "httpstatus", "scstatus", "proxystatuscode"],
    "time": ["timestamp", "time", "edgestarttimestamp", "datetime", "date", "@timestamp", "time_local",
             "timeutc", "requesttimestamp", "ts", "starttime"],
    "ip": ["client_ip", "clientip", "ip", "remote_addr", "remoteaddr", "clientipaddress", "cip", "realip", "c-ip"],
    "referer": ["referer", "referrer", "clientrequestreferer", "http_referer", "requestreferer", "csreferer"],
    "accept": ["accept", "http_accept", "requestaccept", "clientrequestaccept"],
    "method": ["method", "requestmethod", "clientrequestmethod", "http_method"],
    "count": ["count", "requests", "hits"],
}


def _norm(k: str) -> str:
    return re.sub(r"[^a-z0-9@]", "", k.lower())


def build_alias_index(user_map: dict) -> dict:
    idx = {}
    for field, names in ALIASES.items():
        for n in names:
            idx.setdefault(_norm(n), field)
    for field, col in user_map.items():
        idx[_norm(col)] = field
    return idx


def flatten(rec, out=None, prefix_priority=("proxy", "dimensions", "request", "http", "attributes")):
    """Flatten nested dicts; keys from preferred sub-objects win (Vercel proxy, CF GraphQL dimensions)."""
    out = {} if out is None else out
    if not isinstance(rec, dict):
        return out
    for key in prefix_priority:
        sub = rec.get(key)
        if isinstance(sub, dict):
            for k, v in sub.items():
                if not isinstance(v, dict):
                    out.setdefault(k, v)
    for k, v in rec.items():
        if isinstance(v, dict):
            flatten(v, out, ())
        else:
            out.setdefault(k, v)
    return out


def to_record(flat: dict, idx: dict, user_map: dict) -> dict | None:
    rec = {}
    for k, v in flat.items():
        field = idx.get(_norm(k))
        if field and field not in rec and v not in (None, ""):
            rec[field] = v
    if isinstance(rec.get("ua"), list):
        rec["ua"] = rec["ua"][0] if rec["ua"] else ""
    if isinstance(rec.get("referer"), list):
        rec["referer"] = rec["referer"][0] if rec["referer"] else ""
    path = str(rec.get("path", "") or "")
    if path.startswith(("GET ", "POST ", "HEAD ", "PUT ", "DELETE ", "OPTIONS ")):
        parts = path.split()
        rec.setdefault("method", parts[0])
        path = parts[1] if len(parts) > 1 else "/"
    if path.startswith(("http://", "https://")):
        sp = urllib.parse.urlsplit(path)
        rec.setdefault("host", sp.netloc)
        path = (sp.path or "/") + (f"?{sp.query}" if sp.query else "")
    if not path and "ua" not in rec:
        return None
    rec["path"] = path or "/"
    try:
        rec["status"] = int(float(rec.get("status"))) if rec.get("status") not in (None, "-", "") else None
    except (TypeError, ValueError):
        rec["status"] = None
    try:
        rec["count"] = int(rec.get("count", 1) or 1)
    except (TypeError, ValueError):
        rec["count"] = 1
    rec["time"] = parse_time(rec.get("time"))
    return rec


def parse_time(v) -> dt.datetime | None:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)) or re.fullmatch(r"\d{9,19}(\.\d+)?", str(v)):
            n = float(v)
            for div in (1, 1e3, 1e6, 1e9):
                if n / div < 4e9:
                    return dt.datetime.fromtimestamp(n / div, dt.timezone.utc)
        s = str(v).strip()
        m = re.match(r"(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})\s*([+-]\d{4})?", s)
        if m:
            return dt.datetime.strptime(m.group(0).strip() if m.group(7) else m.group(0) + " +0000", "%d/%b/%Y:%H:%M:%S %z")
        s = s.replace("Z", "+00:00")
        s = re.sub(r"(\.\d{6})\d+", r"\1", s)
        t = dt.datetime.fromisoformat(s)
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def open_text(path: str):
    if path == "-":
        return sys.stdin
    raw = open(path, "rb")
    head = raw.read(2)
    raw.seek(0)
    if head == b"\x1f\x8b":
        return io.TextIOWrapper(gzip.GzipFile(fileobj=raw), encoding="utf-8", errors="replace")
    return io.TextIOWrapper(raw, encoding="utf-8", errors="replace")


def detect_format(sample: str) -> str:
    s = sample.lstrip()
    if s.startswith("{") and '"httpRequestsAdaptiveGroups"' in sample or '"httpRequests1mGroups"' in sample:
        return "cf-graphql"
    if s.startswith("[") or s.startswith("{"):
        return "json"
    first = s.splitlines()[0] if s else ""
    if first.startswith("#Version") or first.startswith("#Fields:"):
        return "w3c"
    if COMBINED.match(first):
        return "combined"
    if "," in first or "\t" in first:
        return "csv"
    return "unknown"


def json_flavor(flat: dict) -> str:
    keys = {k.lower() for k in flat}
    if "proxy" in keys or ("deploymentid" in keys and "statuscode" in keys):
        return "vercel"
    if "edgestarttimestamp" in keys or "clientrequestuseragent" in keys or "rayid" in keys:
        return "cloudflare-logpush"
    if "log_type" in keys or ("deploy_id" in keys and "request_id" in keys):
        return "netlify"
    return "json"


def iter_records(path: str, fmt: str, idx: dict, user_map: dict, stats: dict):
    fh = open_text(path)
    text_head = fh.read(65536) if fmt == "auto" or fmt in ("json", "cf-graphql") else ""
    detected = detect_format(text_head) if fmt == "auto" else fmt
    stats["formats"][path] = detected
    if detected in ("json", "cf-graphql"):
        s = (text_head + fh.read()).strip()
        try:
            whole = json.loads(s)
        except json.JSONDecodeError:
            whole = None
        if isinstance(whole, list):
            objs = whole
        elif isinstance(whole, dict):
            objs = list(_cf_groups(whole)) or [whole]
        else:
            objs = []
            for line in s.splitlines():
                line = line.strip().rstrip(",")
                if not line or line in "[]":
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    stats["unparsed"] += 1
                    continue
                objs.extend(o if isinstance(o, list) else [o])
        flavors = collections.Counter()
        for o in objs:
            flat = flatten(o)
            flavors[json_flavor(o if isinstance(o, dict) else {})] += 1
            rec = to_record(flat, idx, user_map)
            if rec is None:
                stats["unparsed"] += 1
                continue
            yield rec
        if flavors:
            stats["formats"][path] = (detected if detected == "cf-graphql" else flavors.most_common(1)[0][0])
        return
    if detected == "combined":
        for line in _chain(text_head, fh):
            if not line.strip():
                continue
            m = COMBINED.match(line)
            if not m:
                stats["unparsed"] += 1
                continue
            g = m.groupdict()
            target = g["target"] or "/"
            host = g.get("vhost") or ""
            if target.startswith("http"):
                sp = urllib.parse.urlsplit(target)
                host, target = sp.netloc, (sp.path or "/") + (f"?{sp.query}" if sp.query else "")
            yield {"ip": g["ip"], "time": parse_time(g["time"]), "method": g["method"], "path": target,
                   "status": int(g["status"]) if g["status"] and g["status"].isdigit() else None,
                   "referer": g.get("referer") or "", "ua": g.get("ua") or "", "host": host.split(":")[0], "count": 1}
        return
    if detected == "w3c":
        fields = []
        for line in _chain(text_head, fh):
            line = line.rstrip("\n")
            if line.startswith("#Fields:"):
                fields = line[len("#Fields:"):].split()
                continue
            if not line or line.startswith("#") or not fields:
                continue
            row = dict(zip(fields, line.split("\t") if "\t" in line else line.split()))
            if row.get("x-host-header") not in (None, "-", ""):
                row["cs(Host)"] = row["x-host-header"]
            if "date" in row and "time" in row:
                row["timestamp"] = f"{row.pop('date')}T{row.pop('time')}+00:00"
            for k in ("cs(User-Agent)", "cs(Referer)"):
                if k in row:
                    row[k] = urllib.parse.unquote(urllib.parse.unquote(row[k])) if row[k] != "-" else ""
            if row.get("cs-uri-query") not in (None, "-", ""):
                row["cs-uri-stem"] = row.get("cs-uri-stem", "/") + "?" + row["cs-uri-query"]
            rec = to_record(row, idx, user_map)
            if rec is None:
                stats["unparsed"] += 1
                continue
            yield rec
        return
    if detected == "csv":
        content = text_head + fh.read()
        dialect = "excel-tab" if "\t" in content.splitlines()[0] and "," not in content.splitlines()[0] else "excel"
        for row in csv.DictReader(io.StringIO(content), dialect=dialect):
            rec = to_record(row, idx, user_map)
            if rec is None:
                stats["unparsed"] += 1
                continue
            yield rec
        return
    raise SystemExit(f"{path}: could not detect the log format; pass --format or --map")


def _chain(head: str, fh):
    buf = head
    if buf:
        lines = buf.split("\n")
        tail = lines.pop()
        for l in lines:
            yield l
        rest = fh.readline()
        yield tail + rest
    for l in fh:
        yield l


def _cf_groups(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("httpRequestsAdaptiveGroups", "httpRequests1mGroups") and isinstance(v, list):
                for g in v:
                    yield g
            else:
                yield from _cf_groups(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _cf_groups(x)


# ------------------------------------------------------------------ assets

ASSET_EXT = re.compile(r"\.(js|mjs|css|map|png|jpe?g|gif|svg|ico|webp|avif|woff2?|ttf|otf|eot|mp4|webm|mp3|wav|ogg|pdf|zip|gz|wasm)$", re.I)
ASSET_PREFIX = ("/_next/static", "/_next/image", "/_astro/", "/static/", "/assets/", "/fonts/", "/_vercel/", "/favicon",
                "/apple-touch-icon", "/site.webmanifest", "/manifest.json", "/cdn-cgi/", "/monitoring")
MACHINE_FILES = ("/robots.txt", "/llms.txt", "/llms-full.txt", "/sitemap", ".md", "/openapi", "/.well-known/")


def is_asset(path: str) -> bool:
    p = path.split("?")[0].lower()
    q = urllib.parse.urlsplit(path).query.lower()
    if "_rsc=" in q:
        return True
    return bool(ASSET_EXT.search(p)) or p.startswith(ASSET_PREFIX)


def machine_file(path: str) -> str | None:
    p = path.split("?")[0].lower()
    if p == "/robots.txt":
        return "robots.txt"
    if p.endswith("/llms.txt"):
        return "llms.txt"
    if p.endswith("/llms-full.txt"):
        return "llms-full.txt"
    if "sitemap" in p and p.endswith((".xml", ".xml.gz", ".txt")):
        return "sitemap"
    if p.endswith((".md", ".mdx")):
        return ".md page"
    if "openapi" in p or p.endswith(("swagger.json", "/openapi.yaml")):
        return "OpenAPI"
    return None


# ------------------------------------------------------------------ IP verification

IP_LISTS = {
    "openai-gptbot": "https://openai.com/gptbot.json",
    "openai-searchbot": "https://openai.com/searchbot.json",
    "openai-chatgpt-user": "https://openai.com/chatgpt-user.json",
    "anthropic": "https://claude.com/crawling/bots.json",
    "perplexity-bot": "https://www.perplexity.ai/perplexitybot.json",
    "perplexity-user": "https://www.perplexity.ai/perplexity-user.json",
    "google-crawlers": "https://developers.google.com/static/crawling/ipranges/common-crawlers.json",
    "google-user-agents": "https://developers.google.com/static/crawling/ipranges/user-triggered-agents.json",
    "google-user-fetchers": "https://developers.google.com/static/crawling/ipranges/user-triggered-fetchers-google.json",
    "bingbot": "https://www.bing.com/toolbox/bingbot.json",
}
AGENT_LISTS = {
    "GPTBot": ["openai-gptbot"], "OAI-SearchBot": ["openai-searchbot"], "ChatGPT-User": ["openai-chatgpt-user"],
    "ClaudeBot": ["anthropic"], "Claude-User": ["anthropic"], "Claude-SearchBot": ["anthropic"],
    "Claude Code": ["anthropic"],
    "PerplexityBot": ["perplexity-bot"], "Perplexity-User": ["perplexity-user"],
    "Googlebot": ["google-crawlers"], "Google-Agent": ["google-user-agents"],
    "Gemini URL context": ["google-user-fetchers"], "Bingbot": ["bingbot"],
}


def load_ip_lists() -> dict:
    nets = {}
    for key, url in IP_LISTS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "read-agent-traffic/2.0 (ip list check)"})
            data = json.load(urllib.request.urlopen(req, timeout=15))
            nets[key] = [ipaddress.ip_network(p.get("ipv4Prefix") or p.get("ipv6Prefix"), strict=False)
                         for p in data.get("prefixes", []) if p.get("ipv4Prefix") or p.get("ipv6Prefix")]
        except Exception as e:
            print(f"warning: could not load {url}: {e}", file=sys.stderr)
    return nets


def verify_ip(agent: str, ip: str, nets: dict) -> str:
    keys = AGENT_LISTS.get(agent)
    if not keys:
        return "no list"
    if not any(k in nets for k in keys):
        return "list unavailable"
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return "no ip"
    for k in keys:
        if any(addr in n for n in nets.get(k, [])):
            return "verified"
    # Claude Code runs on users' machines: an IP outside Anthropic's list is normal.
    return "not in list" if agent != "Claude Code" else "user machine"


# ------------------------------------------------------------------ analysis

def analyze(args) -> dict:
    user_map = dict(kv.split("=", 1) for kv in (args.map.split(",") if args.map else []))
    idx = build_alias_index(user_map)
    stats = {"formats": {}, "unparsed": 0, "assets": 0, "filtered": 0, "rows": 0, "spoofed": collections.Counter()}
    since = dt.date.fromisoformat(args.since) if args.since else None
    until = dt.date.fromisoformat(args.until) if args.until else None
    visits = []
    has = collections.Counter()
    for path in args.files:
        for r in iter_records(path, args.format, idx, user_map, stats):
            stats["rows"] += 1
            if (r.get("method") or "GET").upper() == "OPTIONS":
                stats["filtered"] += 1
                continue
            host = str(r.get("host") or "")
            if args.site and args.site.lower() not in host.lower():
                stats["filtered"] += 1
                continue
            day = r["time"].date() if r.get("time") else None
            if (since and day and day < since) or (until and day and day > until):
                stats["filtered"] += 1
                continue
            if is_asset(r["path"]) and not args.include_assets:
                stats["assets"] += r.get("count", 1)
                continue
            for f in ("ua", "status", "time", "referer", "ip", "host", "accept"):
                if r.get(f):
                    has[f] += 1
            cls, agent, evidence = classify(str(r.get("ua") or ""), r["path"], host, str(r.get("accept") or ""))
            if cls != "human" and cls != "other-bot" and r["path"].split("?")[0].lower().startswith(SCANNER_PATHS):
                stats["spoofed"][agent] += r.get("count", 1)
                cls, agent, evidence = "other-bot", f"scanner claiming {agent}", "path:scanner"
            r.update(cls=cls, agent=agent, evidence=evidence, day=day)
            visits.append(r)
    if not visits:
        raise SystemExit("no page requests found; check --format / --map / --site")

    nets = load_ip_lists() if args.verify_ips else {}
    verification = collections.defaultdict(collections.Counter)
    if nets:
        for v in visits:
            if v["cls"] != "human" and v.get("ip") and v["agent"] in AGENT_LISTS:
                verification[v["agent"]][verify_ip(v["agent"], str(v["ip"]), nets)] += v["count"]

    total = sum(v["count"] for v in visits)
    by_class = collections.Counter()
    by_agent = collections.Counter()
    agent_class = {}
    agent_paths = collections.defaultdict(set)
    agent_errors = collections.Counter()
    pages_by_class = collections.defaultdict(collections.Counter)
    errors = collections.Counter()
    by_day = collections.defaultdict(collections.Counter)
    machine = collections.defaultdict(collections.Counter)
    referrals = collections.Counter()
    referral_pages = collections.defaultdict(collections.Counter)
    scanner_hits = stats["spoofed"]
    for v in visits:
        n = v["count"]
        by_class[v["cls"]] += n
        by_agent[v["agent"]] += n
        agent_class[v["agent"]] = v["cls"]
        page = v["path"].split("?")[0]
        agent_paths[v["agent"]].add(page)
        pages_by_class[v["cls"]][page] += n
        if v.get("status") and v["status"] >= 400:
            errors[(v["agent"], v["cls"], v["status"], page)] += n
            agent_errors[v["agent"]] += n
        if v["day"]:
            by_day[v["day"]][v["cls"]] += n
        mf = machine_file(v["path"])
        if mf:
            machine[mf][v["agent"]] += n
        if v["cls"] == "human":
            src = ai_referral(str(v.get("referer") or ""), v["path"])
            if src:
                referrals[src] += n
                referral_pages[src][page] += n
    days = sorted(by_day)
    return {"stats": stats, "has": has, "total": total, "by_class": by_class, "by_agent": by_agent,
            "agent_class": agent_class, "agent_paths": agent_paths, "agent_errors": agent_errors,
            "pages_by_class": pages_by_class, "errors": errors, "by_day": by_day, "days": days,
            "machine": machine, "referrals": referrals, "referral_pages": referral_pages,
            "scanner_hits": scanner_hits, "verification": verification, "verified_run": bool(nets),
            "files": args.files, "top": args.top}


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "-"


def report(a: dict) -> str:
    out = []
    w = out.append
    top = a["top"]
    st = a["stats"]
    w("# Agent traffic report\n")
    fmts = ", ".join(f"{p} ({f})" for p, f in st["formats"].items())
    span = f"{a['days'][0]} to {a['days'][-1]} ({len(a['days'])} days)" if a["days"] else "unknown dates"
    w(f"Source: {fmts}. Period: {span}. {a['total']:,} page requests analysed; "
      f"{st['assets']:,} asset requests excluded; {st['filtered']:,} filtered; {st['unparsed']:,} lines not parsed.\n")
    missing = [f for f in ("status", "referer", "ip") if not a["has"].get(f)]
    if missing:
        w(f"Fields missing from these logs: {', '.join(missing)}. Sections that need them are empty.\n")
    w("User agents are what each client claims. "
      + ("IP checks against provider lists are in the agents table." if a["verified_run"] else "Run with --verify-ips to check AI bot IPs against the providers' published lists.")
      + "\n")

    w("## Visits by class\n")
    w("| Class | Requests | Share |")
    w("|---|---|---|")
    for c in CLASSES:
        w(f"| {CLASS_LABEL[c]} | {a['by_class'][c]:,} | {pct(a['by_class'][c], a['total'])} |")
    ai_total = sum(a["by_class"][c] for c in ("coding-agent", "ai-user-fetch", "ai-search", "ai-training"))
    w(f"\nAI agents and crawlers together: {ai_total:,} requests ({pct(ai_total, a['total'])}).\n")

    w("## Agents\n")
    head = "| Agent | Class | Requests | Distinct pages | Errors (4xx/5xx) |" + (" IP check |" if a["verified_run"] else "")
    w(head)
    w("|---|---|---|---|---|" + ("---|" if a["verified_run"] else ""))
    for agent, n in a["by_agent"].most_common():
        cls = a["agent_class"][agent]
        if cls == "human":
            continue
        if cls == "other-bot" and n < max(2, a["total"] // 500) and agent not in a["agent_errors"]:
            continue
        ver = ""
        if a["verified_run"]:
            vc = a["verification"].get(agent)
            ver = " " + (", ".join(f"{k} {v}" for k, v in vc.most_common()) if vc else "-") + " |"
        w(f"| {agent} | {cls} | {n:,} | {len(a['agent_paths'][agent]):,} | {a['agent_errors'][agent]:,} |{ver}")
    w("")
    if a["scanner_hits"]:
        w("Likely spoofed, moved to other bots: requests claiming an AI user agent while probing scanner paths (/.env, /wp-login.php, ...): "
          + ", ".join(f"{k} {v}" for k, v in a["scanner_hits"].most_common()) + ".\n")

    w("## Top pages per class\n")
    for c in CLASSES:
        pages = a["pages_by_class"][c]
        if not pages:
            continue
        w(f"### {CLASS_LABEL[c]}\n")
        w("| Page | Requests |")
        w("|---|---|")
        for p, n in pages.most_common(top):
            w(f"| {p} | {n:,} |")
        w("")

    w("## Errors served to agents and bots\n")
    errs = [(k, n) for k, n in a["errors"].items() if k[1] != "human"]
    if not a["has"].get("status"):
        w("No status codes in these logs.\n")
    elif not errs:
        w("No 4xx/5xx responses to agents or bots.\n")
    else:
        w("| Agent | Class | Status | Page | Requests |")
        w("|---|---|---|---|---|")
        order = {"ai-user-fetch": 0, "coding-agent": 1, "ai-search": 2, "ai-training": 3, "other-bot": 4}
        ranked = sorted(errs, key=lambda kv: (order.get(kv[0][1], 5), -kv[1]))
        for (agent, cls, status, page), n in ranked[: top * 3]:
            w(f"| {agent} | {cls} | {status} | {page} | {n:,} |")
        w("")
        blocked = collections.Counter()
        for (agent, cls, status, page), n in errs:
            if status in (401, 403, 429, 503) and cls != "other-bot":
                blocked[agent] += n
        if blocked:
            w("Blocked or rate-limited AI agents (401/403/429/503): "
              + ", ".join(f"{k} {v}" for k, v in blocked.most_common()) + ". Usually a CDN/WAF rule, not robots.txt.\n")
        missing_pages = collections.Counter()
        for (agent, cls, status, page), n in errs:
            if status == 404 and cls in ("coding-agent", "ai-user-fetch"):
                missing_pages[page] += n
        if missing_pages:
            w("Pages agents asked for that do not exist (404 to coding agents and AI fetches): "
              + ", ".join(f"{p} ({n})" for p, n in missing_pages.most_common(top))
              + ". Redirect the guessable ones or write them.\n")

    w("## Machine-readable files\n")
    if not a["machine"]:
        w("No requests for robots.txt, llms.txt, sitemaps, .md pages or OpenAPI files.\n")
    else:
        w("| File | Who requested it |")
        w("|---|---|")
        for f, agents in sorted(a["machine"].items()):
            w(f"| {f} | " + ", ".join(f"{k} {v}" for k, v in agents.most_common(6)) + " |")
        w("")

    w("## Trend by day\n")
    if not a["days"]:
        w("No timestamps parsed.\n")
    else:
        w("| Day | " + " | ".join(CLASS_LABEL[c] for c in CLASSES) + " |")
        w("|---|" + "---|" * len(CLASSES))
        for d in a["days"][-31:]:
            w(f"| {d} | " + " | ".join(f"{a['by_day'][d][c]:,}" for c in CLASSES) + " |")
        w("")

    w("## People arriving from AI answers\n")
    if not a["has"].get("referer"):
        w("No referrer field in these logs; only utm_source tags could be counted.\n")
    if not a["referrals"]:
        w("No human visits with an AI referrer or utm_source tag.\n")
    else:
        humans = a["by_class"]["human"]
        w(f"{sum(a['referrals'].values()):,} human page views ({pct(sum(a['referrals'].values()), humans)} of human views) came from AI products. "
          "Counts are a floor: many AI apps send no referrer.\n")
        w("| Source | Visits | Top landing pages |")
        w("|---|---|---|")
        for src, n in a["referrals"].most_common():
            pages = ", ".join(f"{p} ({c})" for p, c in a["referral_pages"][src].most_common(3))
            w(f"| {src} | {n:,} | {pages} |")
        w("")
    return "\n".join(out) + "\n"


def to_json(a: dict) -> dict:
    return {
        "total": a["total"], "stats": a["stats"],
        "by_class": dict(a["by_class"]),
        "agents": [{"agent": k, "class": a["agent_class"][k], "requests": n, "pages": len(a["agent_paths"][k]),
                    "errors": a["agent_errors"][k], "ip_check": dict(a["verification"].get(k, {}))}
                   for k, n in a["by_agent"].most_common()],
        "top_pages": {c: a["pages_by_class"][c].most_common(a["top"]) for c in CLASSES},
        "errors": [{"agent": k[0], "class": k[1], "status": k[2], "page": k[3], "requests": n}
                   for k, n in a["errors"].most_common(200)],
        "by_day": {str(d): dict(a["by_day"][d]) for d in a["days"]},
        "machine_files": {f: dict(v) for f, v in a["machine"].items()},
        "ai_referrals": {s: {"visits": n, "pages": a["referral_pages"][s].most_common(10)} for s, n in a["referrals"].items()},
        "likely_spoofed": dict(a["scanner_hits"]),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="log files (.gz ok) or - for stdin")
    ap.add_argument("--format", default="auto", choices=["auto", "combined", "json", "cf-graphql", "w3c", "csv"])
    ap.add_argument("--map", help="field mapping for unknown columns, e.g. ua=Agent,path=Uri,status=Code")
    ap.add_argument("--site", help="only count requests whose host contains this")
    ap.add_argument("--since", help="YYYY-MM-DD, inclusive")
    ap.add_argument("--until", help="YYYY-MM-DD, inclusive")
    ap.add_argument("--top", type=int, default=10, help="rows per top-N table (default 10)")
    ap.add_argument("--include-assets", action="store_true", help="count JS/CSS/images/fonts too")
    ap.add_argument("--verify-ips", action="store_true", help="check bot IPs against provider IP lists (network)")
    ap.add_argument("--out", help="markdown report path (default stdout)")
    ap.add_argument("--json", help="also write a JSON summary here")
    args = ap.parse_args()
    a = analyze(args)
    md = report(a)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(md)
        print(f"wrote {args.out}: {a['total']:,} page requests", file=sys.stderr)
    else:
        print(md)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(to_json(a), fh, indent=2, default=str)


if __name__ == "__main__":
    main()
