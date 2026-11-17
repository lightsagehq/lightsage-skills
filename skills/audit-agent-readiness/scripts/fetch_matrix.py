#!/usr/bin/env python3
"""Fetch a site the way AI crawlers, AI assistants and coding agents do, and
write a markdown report of ranked fixes with evidence.

What it does, in order, within a request budget (--max, default 40):
  1. robots.txt: status, rules per AI user agent (RFC 9309 longest match),
     Sitemap: lines, Content-Signal lines.
  2. Sitemaps: /sitemap.xml plus any listed only in robots.txt (index -> 1 child).
  3. llms.txt / llms-full.txt on the site (and on the docs host if different).
  4. Key pages (homepage, docs, pricing or product, one blog post): fetched with
     a browser UA and each AI UA; status, bytes, visible text, challenge pages,
     markdown served to crawlers, noindex, empty-without-JavaScript.
  5. Markdown: Accept: text/markdown negotiation, .md twins, Vary: Accept,
     <link rel="alternate" type="text/markdown">.
  6. Docs path for coding agents: docs page as Claude Code and curl, follow one
     doc link, find and fetch an API reference.

Python 3 stdlib only. One request at a time, --delay seconds apart.

Examples:
  python3 fetch_matrix.py https://example.com
  python3 fetch_matrix.py example.com --docs https://docs.example.com --out report.md
  python3 fetch_matrix.py example.com --pages https://example.com/pricing --max 60 --json raw.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

MAX_BODY = 2_000_000

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HTML_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

# name -> (User-Agent, Accept, purpose)
# purpose: browser | training | search | user | coding
PROFILES = {
    "browser": (BROWSER_UA, HTML_ACCEPT, "browser"),
    "GPTBot": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.3; +https://openai.com/gptbot",
        HTML_ACCEPT, "training"),
    "OAI-SearchBot": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.3; +https://openai.com/searchbot",
        HTML_ACCEPT, "search"),
    "ChatGPT-User": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
        HTML_ACCEPT, "user"),
    "ClaudeBot": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
        HTML_ACCEPT, "training"),
    "Claude-SearchBot": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; +claudebot@anthropic.com)",
        HTML_ACCEPT, "search"),
    "Claude-User": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +Claude-User@anthropic.com)",
        HTML_ACCEPT, "user"),
    "PerplexityBot": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
        HTML_ACCEPT, "search"),
    "Perplexity-User": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Perplexity-User/1.0; +https://perplexity.ai/perplexity-user)",
        HTML_ACCEPT, "user"),
    # Claude Code's WebFetch: names Claude-User, asks for markdown first.
    "Claude Code": (
        "Claude-User (claude-code/2.0.0; +https://support.anthropic.com/)",
        "text/markdown, text/html, */*", "coding"),
    # Codex, Gemini CLI and most coding agents read docs with curl from a shell.
    "curl": ("curl/8.7.1", "*/*", "coding"),
}
HOME_PROFILES = list(PROFILES)
PAGE_PROFILES = ["browser", "OAI-SearchBot", "ChatGPT-User", "Claude-User", "PerplexityBot", "Claude Code"]
DOCS_PROFILES = ["browser", "OAI-SearchBot", "ChatGPT-User", "Claude-User", "PerplexityBot", "Claude Code", "curl"]

# robots.txt product tokens -> purpose. Policy-only tokens never appear in a UA.
ROBOTS_TOKENS = [
    ("OAI-SearchBot", "search", "ChatGPT search results and citations"),
    ("ChatGPT-User", "user", "ChatGPT opening a page a user asked about"),
    ("GPTBot", "training", "OpenAI model training"),
    ("Claude-SearchBot", "search", "Claude search results"),
    ("Claude-User", "user", "Claude (and Claude Code) opening a page for a user"),
    ("ClaudeBot", "training", "Anthropic model training"),
    ("PerplexityBot", "search", "Perplexity search index"),
    ("Perplexity-User", "user", "Perplexity opening a page for a user"),
    ("Googlebot", "search-engine", "Google Search, AI Overviews, AI Mode"),
    ("Bingbot", "search-engine", "Bing, Copilot; feeds other AI search"),
    ("Google-Extended", "policy", "Gemini training and grounding (token only)"),
    ("Applebot-Extended", "policy", "Apple AI training (token only)"),
    ("CCBot", "training", "Common Crawl, used by many model trainers"),
]

CHALLENGE_MARKERS = (
    "just a moment...", "attention required! | cloudflare", "cf-browser-verification",
    "challenge-platform", "cf_chl_", "verify you are human", "checking your browser",
    "access denied", "request unsuccessful. incapsula", "pardon our interruption",
    "px-captcha", "captcha-delivery.com", "you have been blocked", "bot detected",
    "enable javascript and cookies to continue", "vercel security checkpoint",
)
BLOCK_PAGE_MARKERS = ("access denied", "you have been blocked", "bot detected", "request unsuccessful")
API_REF_HINTS = ("api reference", "api-reference", "/reference", "/api/", "/api", "openapi", "rest api")


# ---------------------------------------------------------------- HTTP

class Budget:
    def __init__(self, max_requests: int, delay: float, timeout: float, quiet: bool):
        self.max = max_requests
        self.used = 0
        self.skipped: list[str] = []
        self.delay = delay
        self.timeout = timeout
        self.quiet = quiet
        self.log: list[dict] = []
        self._last = 0.0

    def fetch(self, url: str, profile: str, accept: str | None = None, note: str = "") -> dict:
        ua, default_accept, purpose = PROFILES[profile]
        label = f"{profile}{' ' + note if note else ''}"
        if self.used >= self.max:
            self.skipped.append(f"{label} {url}")
            return {"url": url, "profile": profile, "skipped": True, "status": None}
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0 and self.used:
            time.sleep(wait)
        self.used += 1
        headers = {
            "User-Agent": ua,
            "Accept": accept or default_accept,
            "Accept-Encoding": "gzip, deflate",
        }
        if profile == "browser":
            headers["Accept-Language"] = "en-US,en;q=0.9"
        req = urllib.request.Request(url, headers=headers)
        out = {"url": url, "profile": profile, "purpose": purpose, "accept": headers["Accept"],
               "note": note, "status": None, "final_url": url, "headers": {}, "body": "",
               "bytes": 0, "error": None, "skipped": False}
        start = time.monotonic()
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            out["status"] = resp.status
            out["final_url"] = resp.geturl()
            raw = resp.read(MAX_BODY)
            hdrs = resp.headers
        except urllib.error.HTTPError as e:
            out["status"] = e.code
            out["final_url"] = e.geturl() or url
            try:
                raw = e.read(MAX_BODY)
            except Exception:
                raw = b""
            hdrs = e.headers
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            out["error"] = str(getattr(e, "reason", e))[:200]
            raw, hdrs = b"", None
        out["ms"] = int((time.monotonic() - start) * 1000)
        self._last = time.monotonic()
        if hdrs is not None:
            out["headers"] = {k.lower(): v for k, v in hdrs.items()}
            raw = _decode_body(raw, out["headers"].get("content-encoding", ""))
        elif raw[:2] == b"\x1f\x8b":
            raw = _decode_body(raw, "gzip")
        out["bytes"] = len(raw)
        out["body"] = raw.decode(_charset(out["headers"].get("content-type", "")), errors="replace")
        self.log.append({k: v for k, v in out.items() if k != "body"})
        if not self.quiet:
            print(f"  [{self.used}/{self.max}] {out['status'] or out['error']} {label} {url}", file=sys.stderr)
        return out


def _decode_body(raw: bytes, encoding: str) -> bytes:
    """Decompress gzip/deflate, tolerating bodies cut off at MAX_BODY."""
    encoding = encoding.lower()
    if not raw or not ("gzip" in encoding or "deflate" in encoding or raw[:2] == b"\x1f\x8b"):
        return raw
    for wbits in (16 + zlib.MAX_WBITS, zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            return zlib.decompressobj(wbits).decompress(raw, MAX_BODY * 5)
        except zlib.error:
            continue
    return raw


def _charset(content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    return m.group(1) if m else "utf-8"


def ctype(r: dict) -> str:
    return (r.get("headers", {}).get("content-type") or "").split(";")[0].strip().lower()


def is_html(r: dict) -> bool:
    return ctype(r) in ("text/html", "application/xhtml+xml") or "<html" in r.get("body", "")[:2000].lower()


def is_markdown(r: dict) -> bool:
    if r.get("status") is None or not (200 <= r["status"] < 300):
        return False
    ct = ctype(r)
    body = r.get("body", "").lstrip()
    if ct in ("text/markdown", "text/x-markdown"):
        return bool(body)
    return ct == "text/plain" and body[:1] in "#-*>[" and "<html" not in body[:2000].lower() and bool(body)


# ---------------------------------------------------------------- HTML

class PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "head"}

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.skip = 0
        self.text: list[str] = []
        self.title = ""
        self._in_title = False
        self.meta_description = ""
        self.meta_robots = ""
        self.canonical = ""
        self.md_alternate = ""
        self.links: list[tuple[str, str]] = []
        self._a_href: str | None = None
        self._a_text: list[str] = []
        self.scripts = 0
        self.h1 = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script":
            self.scripts += 1
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self.h1 += 1
        if tag == "meta":
            name = a.get("name", "").lower()
            if name == "description":
                self.meta_description = a.get("content", "")
            if name in ("robots", "googlebot", "gptbot", "oai-searchbot"):
                self.meta_robots += " " + a.get("content", "").lower()
        if tag == "link":
            rel = a.get("rel", "").lower()
            if "canonical" in rel:
                self.canonical = a.get("href", "")
            if "alternate" in rel and "markdown" in a.get("type", "").lower():
                self.md_alternate = urllib.parse.urljoin(self.base, a.get("href", ""))
        if tag == "a" and a.get("href"):
            self._a_href = urllib.parse.urljoin(self.base, a["href"])
            self._a_text = []
        if tag == "body":
            self.skip = 0  # a missing </head> must not hide the body
        if tag in self.SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._a_href:
            if len(self.links) < 400:
                self.links.append((self._a_href, " ".join("".join(self._a_text).split())[:80]))
            self._a_href = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._a_href is not None:
            self._a_text.append(data)
        if not self.skip:
            self.text.append(data)


def parse_page(r: dict) -> dict:
    p = PageParser(r.get("final_url") or r["url"])
    try:
        p.feed(r.get("body", ""))
    except Exception:
        pass
    text = " ".join(" ".join(p.text).split())
    return {"text_len": len(text), "title": " ".join(p.title.split())[:120],
            "meta_description": p.meta_description[:200], "meta_robots": p.meta_robots.strip(),
            "canonical": p.canonical, "md_alternate": p.md_alternate, "links": p.links,
            "scripts": p.scripts, "h1": p.h1, "text_sample": text[:200]}


def challenge_reason(r: dict, baseline_text: int | None = None) -> str | None:
    h = r.get("headers", {})
    for key in ("cf-mitigated", "x-vercel-mitigated"):
        if "challenge" in h.get(key, "").lower():
            return f"{key}: {h[key]}"
    status = r.get("status") or 0
    body = r.get("body", "")[:20000].lower()
    if status >= 400 or (baseline_text and parse_page(r)["text_len"] < 0.4 * baseline_text) or len(body) < 6000:
        for m in CHALLENGE_MARKERS:
            if m in body:
                return f'page contains "{m}"'
    return None


# ---------------------------------------------------------------- robots.txt (RFC 9309)

def parse_robots(body: str) -> dict:
    groups: list[dict] = []
    sitemaps: list[str] = []
    signals: list[str] = []
    current = None
    last_was_agent = False
    for raw in body.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if not last_was_agent or current is None:
                current = {"agents": [], "rules": []}
                groups.append(current)
            current["agents"].append(value.lower())
            last_was_agent = True
            continue
        if key == "sitemap":
            sitemaps.append(value)
        elif key == "content-signal":
            signals.append(value)
        elif key in ("allow", "disallow") and current is not None:
            current["rules"].append((key, value))
        last_was_agent = False
    return {"groups": groups, "sitemaps": sitemaps, "content_signals": signals}


def _pattern_match(pattern: str, path: str) -> bool:
    anchored = pattern.endswith("$")
    pat = pattern[:-1] if anchored else pattern
    regex = "^" + ".*".join(re.escape(part) for part in pat.split("*")) + ("$" if anchored else "")
    return re.match(regex, path) is not None


def robots_decision(robots: dict, token: str, path: str) -> dict:
    token_l = token.lower()
    groups = [g for g in robots["groups"] if token_l in g["agents"]]
    group_name = token
    if not groups:
        groups = [g for g in robots["groups"] if "*" in g["agents"]]
        group_name = "*"
    if not groups:
        return {"allowed": True, "rule": "no matching group", "group": None}
    best = None
    for g in groups:
        for kind, value in g["rules"]:
            if kind == "disallow" and value == "":
                continue
            if _pattern_match(value, path):
                length = len(value)
                if best is None or length > best[0] or (length == best[0] and kind == "allow"):
                    best = (length, kind, value)
    if best is None:
        return {"allowed": True, "rule": "no rule matches", "group": group_name}
    return {"allowed": best[1] == "allow", "rule": f"{best[1].capitalize()}: {best[2]}", "group": group_name}


# ---------------------------------------------------------------- helpers

def norm_site(site: str) -> str:
    if not re.match(r"^https?://", site):
        site = "https://" + site
    parts = urllib.parse.urlsplit(site)
    return f"{parts.scheme}://{parts.netloc}/"


def origin(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def path_of(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    return (p.path or "/") + (f"?{p.query}" if p.query else "")


def md_twin(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    path = p.path or "/"
    path = path + "index.md" if path.endswith("/") else path + ".md"
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, "", ""))


def sitemap_locs(body: str) -> tuple[list[str], bool]:
    locs = [m.strip() for m in re.findall(r"<loc>\s*(.*?)\s*</loc>", body, re.I | re.S)]
    return locs, "<sitemapindex" in body[:2000].lower()


def same_site(url: str, site: str) -> bool:
    a = urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    b = urllib.parse.urlsplit(site).netloc.lower().removeprefix("www.")
    return a == b or a.endswith("." + b)


def pick_pages(site: str, candidates: list[str], docs: str | None) -> list[tuple[str, str]]:
    picked: list[tuple[str, str]] = []
    seen = {site.rstrip("/")}

    def take(kind, pred):
        for u in candidates:
            uu = u.split("#")[0]
            if uu.rstrip("/") in seen or not same_site(uu, site):
                continue
            if re.search(r"\.(png|jpe?g|gif|svg|pdf|zip|xml|css|js)$", uu, re.I):
                continue
            if pred(urllib.parse.urlsplit(uu).path.lower()):
                picked.append((kind, uu))
                seen.add(uu.rstrip("/"))
                return

    if not docs:
        take("docs", lambda p: re.match(r"^/(docs|documentation|developers?|api-reference)(/|$)", p) is not None)
    take("pricing/product", lambda p: re.match(r"^/(pricing|plans|product|products|features|platform)(/|$)", p) is not None)
    take("blog post", lambda p: re.match(r"^/(blog|resources|articles|posts|guides|learn)/[^/]+", p) is not None)
    skip = r"^/(login|signin|sign-in|signup|sign-up|register|account|cart|search|privacy|terms|legal|cookie)"
    for _ in range(3 - len(picked)):
        take("page", lambda p: len(p) > 1 and re.match(skip, p) is None)
    return picked


def find_docs_link(links: list[tuple[str, str]], site: str) -> str | None:
    best = None
    for href, text in links:
        if not href.startswith("http"):
            continue
        host = urllib.parse.urlsplit(href).netloc.lower()
        path = urllib.parse.urlsplit(href).path.lower()
        t = text.lower()
        if host.startswith(("docs.", "developer.", "developers.")) and same_site(href, site):
            return href
        if same_site(href, site) and (re.match(r"^/(docs|documentation|developers?)(/|$)", path)
                                      or t in ("docs", "documentation", "developers", "developer docs")):
            best = best or href
    return best


def find_link(links, base_url, hints, exclude: set[str]) -> str | None:
    for href, text in links:
        h, t = href.lower(), text.lower()
        if href.split("#")[0].rstrip("/") in exclude or not same_site(href, base_url):
            continue
        if any(x in t or x in urllib.parse.urlsplit(h).path for x in hints):
            return href.split("#")[0]
    return None


def first_doc_link(links, docs_url, exclude: set[str]) -> str | None:
    pref = ("quickstart", "getting-started", "get-started", "install", "authentication", "introduction")
    docs_l = [h.split("#")[0] for h, _ in links if same_site(h, docs_url)
              and h.split("#")[0].rstrip("/") not in exclude
              and urllib.parse.urlsplit(h).netloc == urllib.parse.urlsplit(docs_url).netloc
              and not re.search(r"\.(png|jpe?g|svg|css|js)$", h)]
    for h in docs_l:
        if any(p in h.lower() for p in pref):
            return h
    return docs_l[0] if docs_l else None


def ev(r: dict) -> str:
    if r.get("skipped"):
        return f"`{r['profile']}` {r['url']} -> not fetched (budget)"
    status = r.get("status") or f"error: {r.get('error')}"
    extra = ""
    if r.get("final_url") and r["final_url"].rstrip("/") != r["url"].rstrip("/"):
        extra = f", redirected to {r['final_url']}"
    ct = ctype(r) or "-"
    return f"`{r['profile']}` GET {r['url']} -> {status}, {r.get('bytes', 0):,} bytes, {ct}{extra}"


# ---------------------------------------------------------------- audit

def audit(args) -> dict:
    site = norm_site(args.site)
    b = Budget(args.max, args.delay, args.timeout, args.quiet)
    res: dict = {"site": site, "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 "findings": [], "pages": [], "robots": {}, "sitemaps": [], "llms": [], "docs": {}}
    F = res["findings"]

    def finding(sev, title, why, fix, evidence):
        F.append({"severity": sev, "title": title, "why": why, "fix": fix, "evidence": evidence[:12]})

    # 1. robots.txt
    rb = b.fetch(origin(site) + "/robots.txt", "browser", accept="text/plain,*/*")
    robots = parse_robots(rb["body"]) if rb.get("status") and rb["status"] < 300 and not is_html(rb) else {
        "groups": [], "sitemaps": [], "content_signals": []}
    res["robots"] = {"status": rb.get("status"), "error": rb.get("error"), "html": bool(rb.get("status") == 200 and is_html(rb)),
                     "sitemaps": robots["sitemaps"], "content_signals": robots["content_signals"],
                     "groups": len(robots["groups"])}
    st = rb.get("status")
    if rb.get("error") or (st and (st >= 500 or st == 429)):
        finding("P0", f"robots.txt is unreachable ({st or rb.get('error')})",
                "RFC 9309 tells crawlers to treat a 5xx (and Google treats a 429) as 'disallow everything', so compliant AI and search crawlers stop crawling the whole site.",
                "Serve robots.txt with a 200 (or a 404 if you want no rules). Check the CDN/WAF is not challenging /robots.txt.",
                [ev(rb)])
    elif st == 200 and is_html(rb):
        finding("P2", "robots.txt returns an HTML page with 200",
                "Crawlers find no valid rules and treat it as allow-all, so you have no per-bot control; it is usually an SPA fallback route.",
                "Serve a real text/plain robots.txt at the root.", [ev(rb)])

    # 2. homepage (browser) to discover links
    home = b.fetch(site, "browser")
    home_p = parse_page(home)
    res["home_links"] = len(home_p["links"])

    # 3. sitemaps
    sm_candidates = [origin(site) + "/sitemap.xml"] + [s for s in robots["sitemaps"] if s.rstrip("/") != origin(site) + "/sitemap.xml"]
    sm_pages: list[str] = []
    fetched_sm = 0
    for sm_url in sm_candidates[:2]:
        r = b.fetch(sm_url, "browser", accept="application/xml,text/xml,*/*")
        fetched_sm += 1
        locs, is_index = sitemap_locs(r.get("body", "")) if r.get("status") == 200 else ([], False)
        entry = {"url": sm_url, "status": r.get("status"), "listed_in_robots": sm_url in robots["sitemaps"],
                 "index": is_index, "locs": len(locs)}
        res["sitemaps"].append(entry)
        if is_index and locs:
            child = b.fetch(locs[0], "browser", accept="application/xml,text/xml,*/*")
            clocs, _ = sitemap_locs(child.get("body", "")) if child.get("status") == 200 else ([], False)
            entry["first_child"] = {"url": locs[0], "status": child.get("status"), "locs": len(clocs)}
            sm_pages.extend(clocs)
        else:
            sm_pages.extend(locs)
    ok_sm = [s for s in res["sitemaps"] if s["status"] == 200 and (s["locs"] or s.get("first_child"))]
    if not ok_sm:
        finding("P1", "No working sitemap found",
                "Search indexers (OAI-SearchBot, PerplexityBot, Bingbot, Googlebot) find deep pages faster from a sitemap; without one, new docs and posts are found late or not at all.",
                "Publish /sitemap.xml (or a sitemap index) and list it in robots.txt with a `Sitemap:` line.",
                [f"{s['url']} -> {s['status']}" for s in res["sitemaps"]])
    else:
        if not robots["sitemaps"] and st == 200:
            finding("P2", "robots.txt has no `Sitemap:` line",
                    "Crawlers that do not guess /sitemap.xml rely on the robots.txt line to find it.",
                    f"Add `Sitemap: {ok_sm[0]['url']}` to robots.txt.", [f"{ok_sm[0]['url']} -> 200, {ok_sm[0]['locs']} URLs"])
        root = res["sitemaps"][0]
        if root["status"] != 200 and any(s["listed_in_robots"] for s in ok_sm):
            finding("info", "Sitemap lives only at the URL listed in robots.txt",
                    "Fine for crawlers that read robots.txt; tools and audits that only try /sitemap.xml will report 'no sitemap'.",
                    "Optional: redirect /sitemap.xml to the real sitemap.", [f"{root['url']} -> {root['status']}"] + [f"{s['url']} -> 200 (robots.txt)" for s in ok_sm])
    for s in res["sitemaps"]:
        if s["listed_in_robots"] and s["status"] != 200:
            finding("P1", f"Sitemap listed in robots.txt returns {s['status']}",
                    "Crawlers follow the robots.txt line first and get an error.", "Fix or remove the stale `Sitemap:` line.",
                    [f"{s['url']} -> {s['status']}"])

    # pick pages
    docs_url = args.docs or find_docs_link(home_p["links"], site)
    pages: list[tuple[str, str]] = [("homepage", site)]
    if docs_url:
        pages.append(("docs", docs_url))
    if args.pages:
        pages += [("page", u) for u in args.pages]
    else:
        pages += pick_pages(site, [h for h, _ in home_p["links"]] + sm_pages, docs_url)
    pages = pages[: 1 + max(0, args.max_pages)]

    # 4. llms.txt
    llms_hosts = [origin(site)]
    if docs_url and origin(docs_url) != origin(site):
        llms_hosts.append(origin(docs_url))
    for host in llms_hosts:
        for name in ("llms.txt", "llms-full.txt"):
            if host != origin(site) and name == "llms-full.txt":
                continue
            r = b.fetch(f"{host}/{name}", "curl")
            ok = r.get("status") == 200 and not is_html(r) and r.get("body", "").strip() != ""
            body = r.get("body", "")
            res["llms"].append({"url": r["url"], "status": r.get("status"), "ok": ok, "html": r.get("status") == 200 and is_html(r),
                                "bytes": r.get("bytes"), "h1": body.lstrip().startswith("# "),
                                "links": len(re.findall(r"\]\((https?://[^)]+)\)", body)),
                                "relative_links": len(re.findall(r"\]\((/[^)]*)\)", body))})
    for l in res["llms"]:
        if l["html"]:
            finding("P2", f"{l['url'].rsplit('/', 1)[1]} returns your HTML app shell with 200",
                    "Agents that try it get a page of JavaScript, not an index; worse than a clean 404.",
                    "Serve a real markdown file or return 404.", [f"{l['url']} -> 200 text/html"])
    docs_llms = [l for l in res["llms"] if l["url"].endswith("/llms.txt") and (not docs_url or origin(l["url"]) == origin(docs_url))]
    if docs_url and docs_llms and not any(l["ok"] for l in docs_llms):
        finding("P2", "Docs have no llms.txt",
                "Coding agents and people pasting your docs into an agent use it as a map of the docs. It does not affect ChatGPT, Perplexity or Google rankings.",
                "Generate /llms.txt from the docs nav (absolute links to .md pages); add /llms-full.txt for API docs.",
                [f"{l['url']} -> {l['status']}" for l in docs_llms])
    for l in res["llms"]:
        limit = 500_000 if l["url"].endswith("llms-full.txt") else 100_000
        if l["ok"] and (l["bytes"] or 0) > limit:
            finding("info", f"{l['url'].rsplit('/', 1)[1]} is {l['bytes']:,} bytes",
                    "Agent fetch tools truncate or summarise long responses (Claude Code's WebFetch keeps roughly the first 100k characters), so most of the file is never read in one fetch.",
                    "Keep the root llms.txt to a curated index; split full text per section (e.g. /docs/<section>/llms-full.txt) and link those.", [l["url"]])
        if l["ok"] and l["relative_links"] and not l["links"]:
            finding("P2", f"{l['url']} uses only relative links",
                    "An agent holding the file without its URL cannot resolve them.", "Make links absolute.", [l["url"]])

    # 5. page matrix
    baseline_blocked = False
    for kind, url in pages:
        profiles = HOME_PROFILES if kind == "homepage" else DOCS_PROFILES if kind == "docs" else PAGE_PROFILES
        rows = []
        base = home if kind == "homepage" else b.fetch(url, "browser")
        base_p = parse_page(base)
        rows.append(("browser", base, base_p))
        for prof in profiles:
            if prof == "browser":
                continue
            r = b.fetch(url, prof)
            rows.append((prof, r, parse_page(r) if not r.get("skipped") else None))
        md = b.fetch(md_twin(url), "curl", note=".md") if kind in ("homepage", "docs") else None
        page = {"kind": kind, "url": url, "robots": {}, "cells": [], "base_text": base_p["text_len"],
                "title": base_p["title"], "meta_robots": base_p["meta_robots"],
                "x_robots": base.get("headers", {}).get("x-robots-tag", ""), "md_alternate": base_p["md_alternate"],
                "link_header": base.get("headers", {}).get("link", ""), "scripts": base_p["scripts"],
                "md_twin": None}
        for token, purpose, _ in ROBOTS_TOKENS:
            page["robots"][token] = robots_decision(robots, token, path_of(url)) if robots["groups"] else {
                "allowed": True, "rule": "no robots rules", "group": None}
        base_ok = base.get("status") and 200 <= base["status"] < 300 and not challenge_reason(base)
        page["unsampled"] = bool(base.get("skipped"))
        if not base_ok and not base.get("skipped"):
            baseline_blocked = True
        for prof, r, p in rows:
            cell = {"profile": prof, "purpose": PROFILES[prof][2], "status": r.get("status"), "error": r.get("error"),
                    "bytes": r.get("bytes", 0), "text": p["text_len"] if p else None, "ctype": ctype(r),
                    "skipped": r.get("skipped", False), "evidence": ev(r), "vary": r.get("headers", {}).get("vary", "")}
            verdict = "ok"
            reason = None if r.get("skipped") or r.get("error") else challenge_reason(r, page["base_text"] if prof != "browser" else None)
            if r.get("skipped"):
                verdict = "not fetched"
            elif r.get("error"):
                verdict = "error"
            elif reason and r["status"] in (200, 401, 403, 429, 503):
                verdict = "blocked" if any(m in reason for m in BLOCK_PAGE_MARKERS) else "challenge"
                cell["reason"] = reason
            elif r["status"] == 429:
                verdict = "rate-limited"
            elif r["status"] in (401, 403, 406, 451):
                verdict = "blocked"
            elif r["status"] >= 500:
                verdict = "server error"
            elif r["status"] >= 400:
                verdict = f"{r['status']}"
            elif is_markdown(r):
                verdict = "markdown"
            elif prof != "browser" and base_ok and page["base_text"] > 500 and p and p["text_len"] < 0.5 * page["base_text"]:
                verdict = "degraded"
            cell["verdict"] = verdict
            page["cells"].append(cell)
        if md is not None:
            page["md_twin"] = {"url": md["url"], "status": md.get("status"), "markdown": is_markdown(md),
                               "ctype": ctype(md), "evidence": ev(md), "skipped": md.get("skipped")}
        res["pages"].append(page)

        # docs: follow a link and find an API reference
        if kind == "docs" and base_ok:
            exclude = {u.rstrip("/") for _, u in pages}
            api = find_link(base_p["links"], url, API_REF_HINTS, exclude)
            nxt = first_doc_link(base_p["links"], url, exclude | ({api.rstrip("/")} if api else set()))
            if nxt and not api and any(h in nxt.lower() for h in API_REF_HINTS):
                api, nxt = nxt, first_doc_link(base_p["links"], url, exclude | {nxt.rstrip("/")})
            d = res["docs"] = {"url": url, "next": None, "api_ref": None}
            if nxt:
                r = b.fetch(nxt, "curl", note="follow link")
                d["next"] = {"url": nxt, "status": r.get("status"), "text": parse_page(r)["text_len"], "evidence": ev(r)}
            if api:
                r = b.fetch(api, "curl", note="API reference")
                d["api_ref"] = {"url": api, "status": r.get("status"), "text": parse_page(r)["text_len"], "evidence": ev(r)}

    res["requests_used"] = b.used
    res["requests_max"] = b.max
    res["skipped"] = b.skipped
    res["log"] = b.log
    build_findings(res, robots, docs_url, baseline_blocked, finding)
    return res


def build_findings(res, robots, docs_url, baseline_blocked, finding):
    pages = res["pages"]
    if baseline_blocked:
        bad = [p for p in pages if p["cells"] and p["cells"][0]["verdict"] not in ("ok", "not fetched")]
        finding("P0", "The browser baseline itself was blocked or challenged",
                "Your bot protection rejects simple HTTP clients, so every AI crawler and coding agent (none run a full browser) likely gets the same. Results for AI user agents below are not comparable to a browser on these pages.",
                "Check the CDN/WAF bot settings (see references/checks-and-fixes.md) and confirm in real logs which agents get 403/challenges.",
                [p["cells"][0]["evidence"] for p in bad])

    # robots blocks: one finding for agents that answer users, one for training/policy tokens
    blocked: dict[str, dict] = {}
    for p in pages:
        for token, purpose, desc in ROBOTS_TOKENS:
            d = p["robots"].get(token)
            if d and not d["allowed"]:
                e = blocked.setdefault(token, {"purpose": purpose, "group": d["group"], "rule": d["rule"], "urls": []})
                e["urls"].append(p["url"])
    for training in (False, True):
        hits = {t: e for t, e in blocked.items() if (e["purpose"] in ("training", "policy")) == training}
        if not hits:
            continue
        tokens = list(hits)
        grouped: dict[tuple, list[str]] = {}
        for t, e in hits.items():
            grouped.setdefault((e["group"], e["rule"], tuple(e["urls"])), []).append(t)
        evidence = [f"{', '.join(ts)}: group `User-agent: {g}`, rule `{rule}`, on {', '.join(urls[:3])}"
                    + (f" (+{len(urls) - 3} more)" if len(urls) > 3 else "") for (g, rule, urls), ts in grouped.items()]
        if training:
            finding("info", f"robots.txt blocks training/policy tokens: {', '.join(tokens)}",
                    "A business choice, not a defect: it keeps content out of future model training but does not remove you from ChatGPT, Claude or Perplexity search answers (those use the search and user tokens).",
                    "Keep it if intended. If you want models to know your product from memory, allow them.", evidence)
        else:
            own = [t for t, e in hits.items() if e["group"] and e["group"].lower() == t.lower()]
            fix = (f"Delete or narrow the `Disallow` lines in the groups named for these agents ({', '.join(own)})." if own else "")
            star = [t for t, e in hits.items() if e["group"] == "*"]
            if star:
                rules = sorted({hits[t]["rule"] for t in star})
                fix += (f" {', '.join(star)} have no group of their own, so `User-agent: *` ({'; '.join(rules)}) applies. "
                        f"Remove that rule for public pages, or add a named group (e.g. `User-agent: {star[0]}` then `Allow: /`).")
            finding("P0", f"robots.txt blocks agents that answer users: {', '.join(tokens)}",
                    "Search indexers (OAI-SearchBot, Claude-SearchBot, PerplexityBot, Googlebot, Bingbot) that obey it drop these pages from AI answers and citations. Providers say robots.txt may not apply to user-triggered fetchers (ChatGPT-User, Perplexity-User), but the rule still signals a block. Skip this if the block is deliberate (e.g. a publisher licensing content).",
                    fix.strip(), evidence)

    # edge blocks
    bad_by_purpose: dict[str, list] = {}
    for p in pages:
        base = p["cells"][0] if p["cells"] else None
        if not base or base["verdict"] not in ("ok", "markdown"):
            continue
        for c in p["cells"][1:]:
            if c["verdict"] in ("blocked", "rate-limited", "challenge", "server error", "error", "degraded") or re.fullmatch(r"4\d\d", c["verdict"]):
                bad_by_purpose.setdefault(c["purpose"], []).append((p, c))
    def agent_lines(hits):
        lines = []
        for agent in dict.fromkeys(c["profile"] for _, c in hits):
            mine = [(p, c) for p, c in hits if c["profile"] == agent]
            p, c = mine[0]
            total = sum(1 for pg in pages if any(x["profile"] == agent for x in pg["cells"]))
            reason = f"; {c['reason']}" if c.get("reason") else ""
            lines.append(f"{agent}: {c['verdict']} on {len(mine)}/{total} pages, e.g. {c['evidence']}{reason}; "
                         f"browser got {p['cells'][0]['status']} with {p['base_text']:,} chars of text")
        return lines

    answer = [h for purpose in ("user", "search", "coding") for h in bad_by_purpose.get(purpose, [])]
    if answer:
        agents = list(dict.fromkeys(c["profile"] for _, c in answer))
        verdicts = sorted({c["verdict"] for _, c in answer})
        claude = "Claude Code sends `Claude-User` in its user agent, so a rule against Claude-User also blocks Claude Code. " if {"Claude Code", "Claude-User"} & set(agents) else ""
        finding("P1" if verdicts == ["degraded"] else "P0",
                f"The edge serves {'/'.join(verdicts)} to AI agents where a browser gets the page: {', '.join(agents)}",
                "This is enforced by the CDN, WAF, bot protection or the app, so allowing them in robots.txt does not help. " + claude
                + "If curl gets through but named agents do not, the rule matches on the user-agent name.",
                "Allow these agents in the CDN/WAF bot rules (allow verified AI bots, or skip the challenge for these user agents on public pages and docs). This machine is not the providers' IP range, so confirm with server logs before and after.",
                agent_lines(answer))
    if bad_by_purpose.get("training"):
        hits = bad_by_purpose["training"]
        finding("info", f"The edge blocks AI training crawlers: {', '.join(dict.fromkeys(c['profile'] for _, c in hits))}",
                "A business choice: keeps content out of future training data; no effect on live AI answers if the search and user agents get through.",
                "Keep it if intended.", agent_lines(hits))

    # markdown served to crawlers / negotiation
    for p in pages:
        crawler_md = [c for c in p["cells"] if c["purpose"] in ("search", "user", "training") and c["verdict"] == "markdown"]
        base = p["cells"][0]
        if crawler_md and base["ctype"] in ("text/html", ""):
            finding("P1", f"AI crawlers get markdown instead of HTML on {p['url']}",
                    "Serving markdown in place of HTML to OpenAI's crawlers broke ChatGPT citations in a real case. Answer engines expect the same HTML a browser gets.",
                    "Serve markdown only when the request asks for it (`Accept: text/markdown` or a .md URL), never by user agent.",
                    [c["evidence"] for c in crawler_md])
    for p in pages:
        if p["kind"] not in ("homepage", "docs"):
            continue
        cc = next((c for c in p["cells"] if c["profile"] == "Claude Code"), None)
        neg = bool(cc and cc["verdict"] == "markdown")
        twin = p.get("md_twin") or {}
        p["markdown"] = {"accept_negotiation": neg, "md_twin": bool(twin.get("markdown")), "alternate_link": bool(p["md_alternate"]),
                         "link_header": "markdown" in p["link_header"].lower(), "vary_accept": bool(cc and "accept" in cc["vary"].lower())}
        if neg and not p["markdown"]["vary_accept"]:
            finding("P2", f"Markdown negotiation without `Vary: Accept` on {p['url']}",
                    "A CDN can cache the markdown and serve it to browsers and crawlers (or the HTML to agents).",
                    "Send `Vary: Accept` on both representations.", [cc["evidence"]])
        if p["kind"] == "docs" and cc and not cc["skipped"] and not twin.get("skipped") and not neg and not twin.get("markdown"):
            finding("P2", "Docs are HTML-only for coding agents",
                    "Claude Code, Cursor, OpenCode and Copilot ask for `text/markdown`; markdown cuts navigation and script noise so more of the page fits their fetch budget. Optional for marketing pages.",
                    "Serve markdown on `Accept: text/markdown` and at `<page>.md`, with `Vary: Accept`; keep HTML the default.",
                    [x for x in [cc["evidence"] if cc else None, twin.get("evidence")] if x])

    # JS-empty, noindex
    for p in pages:
        base = p["cells"][0] if p["cells"] else None
        if not base or base["verdict"] not in ("ok",):
            continue
        if p["base_text"] < 250 and p["scripts"] >= 1:
            md_ok = p.get("markdown", {}).get("accept_negotiation") or p.get("markdown", {}).get("md_twin")
            finding("P1", f"{p['url']} is nearly empty without JavaScript ({p['base_text']} characters of text)",
                    "ChatGPT, Claude, Perplexity and their crawlers read the HTML as served and do not run JavaScript, so they see an empty page."
                    + (" Coding agents asking for markdown still get content." if md_ok else ""),
                    "Server-render or prerender public pages so the text is in the HTML response.",
                    [base["evidence"] + f", {p['scripts']} script tags"])
        noindex = "noindex" in p["meta_robots"] or "noindex" in p["x_robots"].lower()
        if noindex:
            finding("P1", f"{p['url']} is marked noindex",
                    "Search indexers, including the ones behind AI search, drop noindex pages.",
                    "Remove noindex from public pages you want cited.",
                    [f"meta robots: {p['meta_robots'] or '-'}; X-Robots-Tag: {p['x_robots'] or '-'}"])

    # docs path
    if not docs_url:
        finding("info", "No docs link found on the homepage",
                "Coding agents usually start from search or your homepage; without a visible Docs link they guess URLs. Ignore if you have no developer docs (or pass --docs).",
                "Link Docs / API reference from the main navigation.", [f"{res['site']}: {res.get('home_links', 0)} homepage links checked"])
    d = res.get("docs") or {}
    if d.get("next") and d["next"]["status"] and d["next"]["status"] >= 400:
        finding("P1", "A link inside the docs fails for coding agents",
                "Agents follow links from the docs page they land on; an error there ends the session or sends them to search.",
                "Fix the link or the access rule.", [d["next"]["evidence"]])
    if docs_url and d and not d.get("api_ref"):
        finding("P2", "No API reference link found on the docs page",
                "Coding agents look for an API reference to get exact endpoints and parameters; without one they guess from examples.",
                "Link the API reference (and an OpenAPI file if you have one) from the docs landing page.", [docs_url])
    elif d.get("api_ref") and d["api_ref"]["status"] and d["api_ref"]["status"] >= 400:
        finding("P1", "API reference fails for coding agents", "Agents cannot read exact endpoints.", "Fix access.", [d["api_ref"]["evidence"]])
    elif d.get("api_ref") and d["api_ref"]["text"] is not None and d["api_ref"]["text"] < 250:
        finding("P1", "API reference is nearly empty without JavaScript",
                "curl-based agents (Codex, Gemini CLI and most shells) see no endpoints.",
                "Server-render the reference or publish the OpenAPI file and markdown pages.", [d["api_ref"]["evidence"]])


# ---------------------------------------------------------------- report

SEV_ORDER = {"P0": 0, "P1": 1, "P2": 2, "info": 3}
SEV_LABEL = {"P0": "P0 blocks agents", "P1": "P1 hurts reading", "P2": "P2 improvement", "info": "info"}


def report(res: dict) -> str:
    out = []
    w = out.append
    w(f"# Agent readiness: {res['site']}\n")
    w(f"Fetched {res['started']} with {res['requests_used']} of {res['requests_max']} allowed requests"
      + (f"; {len(res['skipped'])} planned requests skipped (raise --max)" if res["skipped"] else "") + ".\n")
    w("Every finding below comes from a real request. User agents were sent from this machine, not from the providers' IPs, so a CDN that verifies bots by IP can treat the real bots differently: confirm blocks in server logs.\n")
    findings = sorted(res["findings"], key=lambda f: SEV_ORDER[f["severity"]])
    w("## Ranked fixes\n")
    if not findings:
        w("No problems found in the sampled pages.\n")
    for i, f in enumerate(findings, 1):
        w(f"### {i}. [{SEV_LABEL[f['severity']]}] {f['title']}\n")
        w(f"- Why: {f['why']}")
        w(f"- Fix: {f['fix']}")
        w("- Evidence:")
        for e in f["evidence"]:
            w(f"  - {e}")
        w("")

    w("## Fetch matrix\n")
    w("Verdicts: ok, markdown (served markdown), blocked (401/403/406/451), rate-limited (429), challenge (bot check page), degraded (under half the browser's text), server error, error (network), not fetched (budget).\n")
    for p in res["pages"]:
        w(f"### {p['kind']}: {p['url']}\n")
        w("| Agent | Purpose | Status | Bytes | Text chars | Type | Verdict |")
        w("|---|---|---|---|---|---|---|")
        for c in p["cells"]:
            w(f"| {c['profile']} | {c['purpose']} | {c['status'] or c['error'] or '-'} | {c['bytes']:,} | "
              f"{'-' if c['text'] is None else format(c['text'], ',')} | {c['ctype'] or '-'} | {c['verdict']} |")
        if p.get("md_twin"):
            t = p["md_twin"]
            w(f"| .md twin (curl) | coding | {t['status'] or '-'} | | | {t['ctype'] or '-'} | {'markdown' if t['markdown'] else 'none'} |")
        w("")
        if p.get("markdown"):
            m = p["markdown"]
            w(f"Markdown: Accept negotiation {'yes' if m['accept_negotiation'] else 'no'}, .md twin {'yes' if m['md_twin'] else 'no'}, "
              f"`<link rel=alternate type=text/markdown>` {'yes' if m['alternate_link'] else 'no'}, Link header {'yes' if m['link_header'] else 'no'}, "
              f"Vary: Accept {'yes' if m['vary_accept'] else 'no'}.\n")

    w("## robots.txt per AI user agent\n")
    r = res["robots"]
    w(f"Status {r['status'] or r['error']}; {r['groups']} groups; Sitemap lines: {(', '.join(r['sitemaps'][:5]) + (f' (+{len(r["sitemaps"]) - 5} more)' if len(r['sitemaps']) > 5 else '')) or 'none'}; "
      f"Content-Signal: {'; '.join(r['content_signals']) or 'none'}.\n")
    if res["pages"]:
        heads = [p["kind"] for p in res["pages"]]
        w("| Token | Purpose | " + " | ".join(heads) + " |")
        w("|---|---|" + "---|" * len(heads))
        for token, purpose, desc in ROBOTS_TOKENS:
            cells = []
            for p in res["pages"]:
                d = p["robots"][token]
                cells.append("allowed" if d["allowed"] else f"**blocked** ({d['rule']}, group {d['group']})")
            w(f"| {token} | {purpose}: {desc} | " + " | ".join(cells) + " |")
        w("")

    w("## Sitemaps and llms.txt\n")
    for s in res["sitemaps"]:
        child = s.get("first_child")
        w(f"- {s['url']}: {s['status']}{', listed in robots.txt' if s['listed_in_robots'] else ''}"
          f"{', sitemap index' if s['index'] else ''}, {s['locs']} entries"
          + (f"; first child {child['url']}: {child['status']}, {child['locs']} URLs" if child else ""))
    for l in res["llms"]:
        state = "ok" if l["ok"] else ("HTML app shell" if l["html"] else "missing")
        w(f"- {l['url']}: {l['status']} ({state}{', ' + format(l['bytes'], ',') + ' bytes, ' + str(l['links']) + ' absolute links' if l['ok'] else ''})")
    d = res.get("docs") or {}
    if d:
        w("\n## Docs path for coding agents\n")
        w(f"- Docs page: {d['url']}")
        w(f"- Followed link: {d['next']['evidence'] if d.get('next') else 'none found'}")
        w(f"- API reference: {d['api_ref']['evidence'] if d.get('api_ref') else 'no link found'}")
    w("\n## Not verified by this script\n")
    w("- What the real bots get from their own IPs (check server/CDN logs or the CDN's bot analytics).")
    w("- Pages rendered with JavaScript (this script reads raw HTML, like the agents do).")
    w("- Whether answer engines actually cite or recommend the site (that needs repeated prompt runs).")
    w("- Pages outside the sample; rerun with --pages for specific URLs.")
    if res["skipped"]:
        w(f"- Skipped for budget: {len(res['skipped'])} requests, e.g. {res['skipped'][0]}")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", help="site root, e.g. https://example.com or example.com")
    ap.add_argument("--docs", help="docs landing URL if not linked from the homepage (e.g. https://docs.example.com)")
    ap.add_argument("--pages", nargs="*", help="extra page URLs to test instead of auto-picked ones")
    ap.add_argument("--max", type=int, default=40, help="maximum HTTP requests (default 40)")
    ap.add_argument("--max-pages", type=int, default=3, help="pages besides the homepage (default 3)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
    ap.add_argument("--timeout", type=float, default=15.0, help="per-request timeout in seconds (default 15)")
    ap.add_argument("--out", help="write the markdown report here (default: stdout)")
    ap.add_argument("--json", help="also write raw results as JSON here")
    ap.add_argument("--quiet", action="store_true", help="no per-request progress on stderr")
    args = ap.parse_args()
    res = audit(args)
    md = report(res)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(md)
        print(f"wrote {args.out} ({res['requests_used']} requests, {len(res['findings'])} findings)", file=sys.stderr)
    else:
        print(md)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(res, fh, indent=2, default=str)


if __name__ == "__main__":
    main()
