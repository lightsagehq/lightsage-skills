# Checks and fixes

Read when writing the fix for a finding from `fetch_matrix.py`, or when the user needs CDN-specific steps.

Contents
1. Severity rules
2. robots.txt
3. Edge blocks (CDN, WAF, bot protection)
4. Empty without JavaScript, noindex, thin pages
5. Markdown for coding agents
6. llms.txt and llms-full.txt
7. Sitemaps
8. Docs path for coding agents
9. Reproduce by hand

## 1. Severity rules

| Severity | Meaning | Examples |
|---|---|---|
| P0 blocks agents | An agent that answers users or writes code cannot get the page | robots.txt Disallow for OAI-SearchBot / Claude-SearchBot / PerplexityBot / Googlebot / Bingbot on key pages; 403, 429 or a challenge for ChatGPT-User, Claude-User, Perplexity-User or coding agents; robots.txt returning 5xx; the browser baseline challenged |
| P1 hurts reading | The agent gets the page but little or misleading content | Empty without JavaScript; noindex on pages you want cited; markdown served to crawlers by user agent; no working sitemap; a broken link inside the docs |
| P2 improvement | Helps, mostly coding agents | Markdown negotiation and `.md` twins for docs; `Vary: Accept`; llms.txt for docs; `Sitemap:` line in robots.txt; API reference linked from the docs landing page |
| info | Business choice or context | Training crawlers blocked; sitemap only at a robots.txt-listed URL; oversized llms files |

Rank P0 by reach: user-triggered fetchers and search indexers first (they decide live answers and citations), then coding agents on docs, then everything else. Within a level, a site-wide rule beats a single page.

## 2. robots.txt

Matching (RFC 9309): a crawler uses the group naming its token (case-insensitive); only if none exists does it use `User-agent: *`. Inside the group, the longest matching path wins; on a tie, Allow wins. A named group replaces `*` entirely, so a `User-agent: GPTBot` group with only `Disallow: /private` lets GPTBot read everything else even if `*` says `Disallow: /`.

Common fixes:
```
# Allow AI search and user-triggered fetchers everywhere public
User-agent: OAI-SearchBot
User-agent: ChatGPT-User
User-agent: Claude-SearchBot
User-agent: Claude-User
User-agent: PerplexityBot
User-agent: Perplexity-User
Allow: /
Disallow: /app/

# Training opt-out, if the owner wants it
User-agent: GPTBot
User-agent: ClaudeBot
User-agent: CCBot
User-agent: Google-Extended
User-agent: Applebot-Extended
Disallow: /

User-agent: *
Allow: /
Disallow: /app/

Sitemap: https://example.com/sitemap.xml
```
- Put several `User-agent` lines directly above one rule set to share it. A blank line or rule between them starts a new group.
- `Content-Signal: search=yes, ai-input=yes, ai-train=no` (Cloudflare's convention) declares preferences; nothing enforces it. Ask the owner about `ai-train`.
- Status: serve 200 text/plain. 5xx = "disallow all" for compliant crawlers; 404 = "no rules".

## 3. Edge blocks (CDN, WAF, bot protection)

Signs in the report: 403/429/503 for named AI user agents while the browser and `curl` get 200; `cf-mitigated: challenge` or `x-vercel-mitigated: challenge` headers; "Just a moment...", "Vercel Security Checkpoint", "Access denied", captcha pages.

Where to look (names change; ask the user to check the current dashboard):
- Cloudflare: Security > Bots (Block AI bots, Bot Fight Mode, Super Bot Fight Mode), AI Crawl Control (per-crawler allow/block), WAF custom rules matching user agents, managed robots.txt. New zones block AI crawlers by default. Allow verified bots, or add a skip rule for the search and user-triggered agents on public paths.
- Vercel: Firewall custom rules, Bot Protection and AI bot managed rulesets, Attack Challenge Mode (challenges every non-browser while on).
- Netlify, Fastly, Akamai, AWS WAF, DataDome, HUMAN: bot manager "verified bots" lists; add the AI search and user-triggered agents, scoped to public pages and docs.
- App middleware: user-agent deny lists in Next.js middleware, nginx `if ($http_user_agent ~* ...)`, WordPress security plugins.

Rate limits: AI fetchers can burst (an assistant opening several pages for one answer). A 429 on the second request of a session is a block in practice. Raise limits for verified AI bots rather than allowing everyone.

Verification beats user-agent matching: allow real bots by provider IP lists or reverse DNS (see ai-user-agents.md) so spoofers do not get the same pass.

## 4. Empty without JavaScript, noindex, thin pages

- Under ~250 characters of visible text in the raw HTML with scripts present = client-rendered. Fix with server rendering, static generation or prerendering for public routes (marketing, docs, blog, pricing). App screens behind login do not need it.
- The script reads raw HTML. If the user says "but the page has content", have them run `curl -s <url> | grep -c '<their headline text>'`.
- `noindex` in meta robots or `X-Robots-Tag` removes the page from search indexes that AI search draws on. Common on docs previews and staging rules copied to production.
- Under ~800 characters is thin: agents answer from it poorly; add the actual facts (what it does, pricing, limits, examples).

## 5. Markdown for coding agents

Claude Code, Cursor, OpenCode and Copilot send `Accept: text/markdown` (with HTML as fallback). Done well:
- Same URL, negotiated by `Accept` with q-values: prefer markdown only when the client names `text/markdown` with q >= its HTML q. `*/*` alone gets HTML.
- `Vary: Accept` on both representations, or the CDN caches one for everyone.
- Also serve `<page>.md` (`/index.md` for the root) and advertise it with `<link rel="alternate" type="text/markdown" href="...">` and a `Link` header.
- Absolute links inside the markdown, pointing at other `.md` pages.
- Never choose markdown by user agent. Answer engines must get the same HTML a browser gets.

## 6. llms.txt and llms-full.txt

- Useful for coding agents and people pasting docs into an agent; not used by answer engines for ranking or citation.
- Root file: an H1, one-line summary, curated sections of absolute links to `.md` pages. Keep it under ~100 KB; agent fetch tools truncate long responses.
- llms-full.txt: the full docs text in one file, generated from the same source as the pages. Split per section when it passes a few hundred KB.
- A 200 HTML app shell at /llms.txt is worse than a 404.

## 7. Sitemaps

- List every sitemap in robots.txt with `Sitemap:` (absolute URL). Indexes are fine; gzip is fine.
- Include docs and blog sitemaps, even on other hosts (the docs host should list its own).
- Keep `<lastmod>` honest; search indexers use it to schedule recrawls.

## 8. Docs path for coding agents

A coding agent typically: searches or guesses a docs URL, fetches it (WebFetch or curl), follows one or two links, looks for an API reference or OpenAPI file, then writes code. Failure points to report:
- No docs link from the homepage; docs on a host the agent would not guess.
- Docs or API reference blocked for `curl` or `Claude-User`.
- API reference rendered client-side (empty for curl), or only interactive.
- Links inside docs that 404; versioned URLs that changed without redirects.
- No OpenAPI file or markdown export for the reference.

## 9. Reproduce by hand

```bash
UA='Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot'
curl -s -o /dev/null -w '%{http_code} %{size_download} %{content_type}\n' -A "$UA" https://example.com/
curl -sI -H 'Accept: text/markdown' https://example.com/docs | grep -iE '^(content-type|vary)'
curl -s https://example.com/robots.txt | sed -n '1,80p'
```
