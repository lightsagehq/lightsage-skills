---
name: read-agent-traffic
description: "Which AI agents and bots visit my site, what do they read, and where do they hit errors? Is ChatGPT or Claude Code actually reading our docs, are we blocking GPTBot or ClaudeBot, how much traffic comes from ChatGPT or Perplexity? Use when someone has server or CDN logs (nginx, Apache, Vercel, Cloudflare, Netlify, CloudFront, a CSV export) and wants AI crawler and agent traffic, bot vs human split, pages agents read, 403s or 404s served to agents, or referrals from AI answers. Not for checking whether agents can reach the site without logs (use audit-agent-readiness), or for how often AI answers mention the brand (use measure-ai-visibility)."
license: MIT
metadata:
  version: "2.0.0"
---

# Read agent traffic

Turn the logs the user already has into an answer to: which AI agents and bots visit, what they read, where they fail, and how many people arrive from AI answers.

Rules that must survive:
- A user agent is a claim. Say "declared" unless IPs were checked (`--verify-ips`); never call traffic "verified GPTBot" without it.
- Report counts with the period and the source (CDN vs origin, sampled or not). No percentages without the denominator.
- Most AI agents do not run JavaScript, so client-side analytics (GA4, most product analytics) misses them. Only server or CDN logs answer this; say so if the user only has JS analytics.
- Logs can hold IPs and personal data: process them locally, do not paste raw lines into the chat beyond a few examples, do not upload them anywhere.

## Before you start

1. Find the logs. Ask which host or CDN serves the site and docs; read [references/log-sources.md](references/log-sources.md) when the user needs to export them (Vercel, Cloudflare, Netlify, CloudFront, nginx, Apache).
2. Check coverage: a CDN log sees cached hits; an origin log behind a CDN misses them. Docs on another host (docs.example.com, a docs platform) need their own logs.
3. Prefer at least 7 days; 28 or more for trends. Note the time zone (most exports are UTC).

If the `lightsage` MCP server or CLI is available, read "If Lightsage is connected" first: it may answer without any export.

## Steps

1. Run the analyzer (formats are auto-detected; `.gz` and several files at once are fine):
   ```bash
   python3 scripts/analyze_logs.py access.log* --out agent-traffic.md --json agent-traffic.json
   ```
   Useful flags: `--site docs.example.com` (one host), `--since/--until YYYY-MM-DD`, `--verify-ips` (checks AI and search bot IPs against provider lists; makes ~10 small downloads), `--map ua=Agent,path=Uri,status=Code` for unknown column names, `--include-assets`. Run `--help` for all. Try it on `scripts/fixtures/combined.log` if you need to see the output first.
2. If it says "could not detect" or a section is empty because a field is missing, fix the input (`--map`, a different export with user agent, path, status, time, referrer) rather than guessing.
3. Read the report and answer the user's question first, then these, in order:
   - Blocks: AI fetchers (ChatGPT-User, Claude-User, Perplexity-User) or coding agents getting 401/403/429/503. These are lost answers and failed integrations; usually a CDN/WAF rule. Hand off to `audit-agent-readiness` to reproduce and fix.
   - 404s to coding agents and AI fetches: guessed URLs (`/docs/quickstart.md`, old versions). Redirect the guessable ones, add `.md` twins, or write the missing page.
   - What each class reads: user-triggered fetches show what people ask assistants about (pricing, integrations); coding agents show which docs matter for integrations; search crawlers show what can be cited.
   - Machine files: who reads robots.txt, llms.txt, sitemaps, `.md` pages. llms.txt hits come almost only from coding agents and scripts.
   - People from AI answers: sessions with AI referrers or `utm_source=chatgpt.com`, and their landing pages.
   - Trend: day by day per class; call out changes over 2x, not noise.
4. Write the answer in chat, not only in the report file: a one-paragraph summary with numbers and period; every block (name each status, 403 and 429 alike, with the agent and count); the top 3 to 5 findings each with evidence (agent, page, status, count) and an action; people arriving from AI answers with the count and "this is a floor"; and what the logs could not show. Read [references/classification.md](references/classification.md) when the user asks how traffic was classified, disputes a number, or sees an agent you need to place.

## Gotchas

- Separate user-triggered fetches (ChatGPT-User, Claude-User, Perplexity-User) from crawlers (GPTBot, ClaudeBot, OAI-SearchBot, PerplexityBot). A fetch is a person asking about you right now; a crawl is indexing or training. Lumped together, crawlers look like your biggest readers.
- Claude Code sends `Claude-User (claude-code/...)`: it is a coding agent, not Claude chat. Most other coding agents (Codex, Gemini CLI, Copilot CLI) read docs with plain `curl`, `node` or `python-requests` and no agent name. The analyzer counts those as unnamed coding agents only on docs paths; elsewhere they are scripts. Say this when reporting coding-agent numbers: it is an estimate, and a floor for named agents.
- Spoofing is common: scanners wear GPTBot or ClaudeBot user agents to get past bot rules. Requests from AI user agents to `/.env`, `/wp-login.php` and similar are moved to other bots. For real verification, use `--verify-ips` (provider IP lists) or reverse DNS; Claude Code runs on users' machines, so its IPs never match a provider list.
- Googlebot and Bingbot are counted as other bots, but they feed Google AI Overviews, AI Mode, Copilot and AI search products that use Bing. A drop there matters for AI answers too.
- AI referrals are a floor. Many AI apps and in-app browsers send no referrer; ChatGPT tags many links with `utm_source=chatgpt.com`, which the analyzer counts. Desktop apps often look like direct traffic.
- Next.js prefetches (`?_rsc=`), assets and health checks inflate counts; the analyzer drops them unless `--include-assets`.
- Sampled sources (Cloudflare GraphQL adaptive groups) return estimates; say "about".
- A 403 to ClaudeBot or GPTBot may be a deliberate training opt-out. Ask before calling it a problem. A 403 to ChatGPT-User, Claude-User or a coding agent is almost never intended.
- Don't conclude "no AI traffic" from JS analytics or a short window. Coding-agent traffic is bursty (one integration session can be 20 docs pages in two minutes).

## If Lightsage is connected

Lightsage agent analytics records coding-agent, AI-assistant, AI-search, AI-training, bot and human visits to a site continuously, including agents that do not run JavaScript, so there are no log exports to plumb. Use it when the site is connected; fall back to logs for periods or hosts it does not cover.

1. Check the connection: the `lightsage` MCP server's `status-auth-status-get` tool (CLI: `lightsage status auth-status-get`). If it fails or no server or CLI is present, use the log path above.
2. Find the site: `agent-analytics-sites-list` returns every site with tracked visits and its `site_id`. If the site is missing, tell the user to connect it in the Lightsage app.
3. Read, all read-only and free of credits:
   - `agent-analytics-summary-retrieve`: visits by traffic type for the range, with the previous period for comparison.
   - `agent-analytics-sources-list`: each coding agent and bot with its type and visit count.
   - `agent-analytics-pages-list`: pages agents and bots read, per traffic type; filter by `type` or by one `agent`.
   - `agent-analytics-error-pages-list`: pages that returned 400 and up, with who got each error; `status=404` for missing pages. Its `status_codes_tracked` says whether the site records status codes.
   - `agent-analytics-countries-list`: agent and AI-assistant visits per country.
   For CLI equivalents, find the matching command under `lightsage agent-analytics` with `lightsage --usage`, then `--help`.
4. Report the same way as above (blocks, 404s, what each class reads, trend vs previous period). Use `audit-agent-readiness` to reproduce and fix any block you find.
