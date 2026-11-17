---
name: audit-agent-readiness
description: "Can ChatGPT, Claude, Perplexity and coding agents actually reach and read my site and docs? Is robots.txt or Cloudflare blocking AI bots, are pages empty without JavaScript, do we serve markdown or llms.txt? Use when someone asks to check AI crawler access, agent readiness or AI-friendliness of a site, why ChatGPT or Claude can't open a page, or whether Claude Code or Codex can use their docs. Checks by fetching as each agent, not from a checklist. Not for which bots actually visited (use read-agent-traffic), how often AI answers mention the brand (use measure-ai-visibility), or whether agents complete tasks with an API (use test-api-on-agents)."
license: MIT
metadata:
  version: "2.0.0"
---

# Audit agent readiness

Find out, by fetching for real, whether AI search crawlers, AI assistants and coding agents can reach and read a site and its docs, and return ranked fixes with evidence.

Rules that must survive:
- Every finding carries evidence: URL, user agent, status, bytes or the robots.txt rule. No finding from a checklist alone.
- A block can be deliberate (publishers, training opt-outs). Ask before calling it a bug; blocking training crawlers is a business choice, never a P0.
- Stay polite: one request at a time, the default budget of 40 requests. Raise `--max` only for a site the user owns.
- Never recommend a myth as a fix (see Gotchas). Say what you could not verify.

## Before you start

Get, or infer and state:
1. The site root and the docs URL if docs live elsewhere (`docs.example.com`, `/docs`).
2. Which readers matter: answer engines (ChatGPT, Claude, Perplexity, Google AI), coding agents (Claude Code, Codex, Cursor, Copilot), or both. Marketing sites care most about the first; devtools about both.
3. The CDN or host (Cloudflare, Vercel, Netlify, Fastly, Akamai) and whether the user can change its bot settings. Response headers in the report usually reveal it.
4. Whether any AI blocking is intentional (training opt-out, paywall, licensing).

If the `lightsage` MCP server or CLI is available, read "If Lightsage is connected" first.

## Steps

1. Run the fetch matrix (about one minute at the default rate):
   ```bash
   python3 scripts/fetch_matrix.py https://example.com --docs https://docs.example.com \
     --out agent-readiness.md --json agent-readiness.json
   ```
   Add `--pages <url> ...` for pages that matter (pricing, a top docs page, a page ChatGPT should cite). Run `--help` for flags. It checks robots.txt per AI user agent (RFC 9309 longest-match), sitemaps including ones listed only in robots.txt, llms.txt / llms-full.txt, each key page as a browser and as each AI agent, markdown negotiation and `.md` twins, and the docs path a coding agent takes (docs page, one followed link, the API reference).
2. Read `agent-readiness.md`. Reproduce each P0 by hand before reporting it, for example `curl -s -o /dev/null -w '%{http_code} %{size_download}\n' -A '<UA from the report>' <url>`. Drop findings that do not apply (no docs, deliberate blocks) and say why.
3. Separate the three layers, because the fix lives in different places:
   - Policy: robots.txt rules (site repo or CDN-managed robots.txt).
   - Enforcement: CDN/WAF/bot protection returning 403, 429 or a challenge page (CDN dashboard). robots.txt allowing a bot does not help here.
   - Content: empty-without-JavaScript pages, noindex, markdown served by user agent (app code).
   Read [references/checks-and-fixes.md](references/checks-and-fixes.md) when writing the fix for any finding, or when the user's CDN needs specific steps.
4. Optional, for devtools: one real coding-agent check. Ask first ("this runs 1 to 3 agent sessions on your Claude Code or Codex subscription"). In a fresh temp dir, ask the agent to use only the docs URL to find how to authenticate and make one call; record every URL it fetched and where it stalled. For pass rates across tasks and agents, hand off to `test-api-on-agents`.
5. Write the answer in this shape:
   - One-line verdict per reader: answer engines / coding agents: can reach and read, partly, or blocked.
   - Ranked fixes (P0 blocks agents, P1 hurts reading, P2 improvement), each with evidence, the fix, and who owns it (CDN admin, web team, docs team).
   - What was not verified, and the next check (server logs via `read-agent-traffic`).
   - Myths the user asked about, answered in one line each.

Read [references/ai-user-agents.md](references/ai-user-agents.md) when the user asks which bot does what, which robots.txt token to use, or how to verify a bot is real.

## Gotchas

- Results come from this machine's IP, not OpenAI's or Anthropic's. CDNs that verify bots by IP range or signature can treat the real bot differently (better or worse). A 403 here is strong evidence; a 200 is not proof. Confirm in logs.
- `curl` getting 200 while `ChatGPT-User` gets 403 means a user-agent rule (often a "block AI bots" toggle), not rate limiting.
- Claude Code fetches with `Claude-User (claude-code/...)` in its user agent. A rule blocking Claude-User also blocks Claude Code. Codex and Gemini CLI usually read docs with plain `curl` from a shell.
- If the browser baseline itself gets a challenge, the site's bot protection rejects any client that is not a full browser. That includes every AI agent, so treat it as P0, not as a broken test.
- New Cloudflare zones block known AI crawlers by default, and Cloudflare's managed robots.txt adds training disallows. Check the dashboard even when the repo's robots.txt looks open.
- A robots.txt that returns 5xx tells compliant crawlers to stay off the whole site (RFC 9309); Google treats 429 the same. A 404 means "no rules". An SPA that answers /robots.txt with HTML gives you no rules at all.
- Sitemaps listed only in robots.txt are easy to miss; tools that only try /sitemap.xml report "no sitemap" when there is one.
- Serve markdown when the request asks for it (`Accept: text/markdown` or a `.md` URL), never by user agent. In one real case, returning markdown to OpenAI's crawlers in place of HTML broke ChatGPT citations. Keep `Vary: Accept` on both versions.
- Chat assistants and AI crawlers do not run JavaScript. A page with a few hundred characters of server-rendered text is empty to them, even if markdown negotiation rescues coding agents.
- `Google-Extended` and `Applebot-Extended` are robots.txt tokens, not crawlers; you never see them in logs or fetch as them. Blocking Google-Extended does not remove you from Google Search or AI Overviews (Googlebot governs those).
- Push back on myths: llms.txt is not a ranking or citation signal for ChatGPT, Perplexity or Google (it helps coding agents pointed at docs); meta keywords do nothing; "AI meta tags", ai.txt and hidden "for AI" text are read by no major agent; JSON-LD helps search indexes, not the model directly; allowing GPTBot does not get you cited (training is not search). Full list: [references/myths.md](references/myths.md).

## If Lightsage is connected

Lightsage site audits check every important page of a site for agent access, content delivery, metadata and docs reachability, render pages the way browsing agents see them, and keep the results over time with recommended fixes. Use them to go beyond this sample of pages and to track fixes.

1. Check the connection: the `lightsage` MCP server's `status-auth-status-get` tool (CLI: `lightsage status auth-status-get`). If it fails or no server or CLI is present, stay on the open path above.
2. Read existing results: the `lightsage` MCP server's `site-audits-list` tool (CLI: `lightsage site-audits list`) returns each audited page with its score, priority, issues, evidence and recommended fixes. `site-audits-retrieve` (CLI: `lightsage site-audits retrieve`) returns one page. Both read stored data; they do not start a crawl or spend credits.
3. If there are no audits yet, tell the user to set up the site audit in the Lightsage app; do not try to start one from here.
4. Merge: use Lightsage's page-level issues for coverage and this script's fetch matrix for per-agent evidence (it fetches as each AI user agent, which a page audit may not show). Report one ranked list, not two.
5. To see which agents actually hit the site and which pages fail for them, use `read-agent-traffic`; with Lightsage it reads agent analytics without log exports.
