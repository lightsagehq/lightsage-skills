# How traffic is classified

Read when the user asks how a number was produced, disputes a class, or sees an agent the analyzer does not name. Checked November 2026; new agents appear monthly, so treat unnamed traffic as a prompt to look, not as noise.

Contents
1. Classes
2. Rules, in order
3. Verification and spoofing
4. AI referrals from people
5. Adding an agent

## 1. Classes

| Class | What it is | Examples |
|---|---|---|
| coding-agent | An agent fetching while writing code for someone | Claude Code, Codex, OpenCode, Copilot, Gemini CLI, Aider, Cline; curl and HTTP libraries reading docs |
| ai-user-fetch | An assistant opening a page because a person asked | ChatGPT-User, OAI-Operator, Claude-User, Perplexity-User, Google-Agent, Gemini-Deep-Research, MistralAI-User, meta-externalfetcher, DeepSeekBot |
| ai-search | An AI company's search indexer | OAI-SearchBot, Claude-SearchBot, PerplexityBot, DuckAssistBot, YouBot, AzureAI-SearchBot, Exa and Linkup crawlers |
| ai-training | Collects pages for model training | GPTBot, ClaudeBot, anthropic-ai, CCBot, Bytespider, meta-externalagent, AI2Bot, Cohere's training crawler |
| other-bot | Search engines, SEO tools, link previews, monitors, scripts, empty user agents, spoofed AI user agents | Googlebot, Bingbot, Applebot, AhrefsBot, Slackbot, HeadlessChrome, python-requests on non-docs pages |
| human | A browser-shaped user agent that matched nothing above | Chrome, Safari, Firefox |

## 2. Rules, in order

1. Empty user agent: other-bot.
2. A token naming a coding agent: `claude-code`, `githubcopilotruntime`, `codex`, `opencode`, `openclaw`, `google-gemini-cli`, `googleagent-urlcontext`, `trae/`, `kiro`, `zed/`, `augment.cli`, `devin/`, `aider/`, `qwencode/`, `cline.bot`, `crush/`, `goose/`, `modelcontextprotocol/` (the reference MCP fetch server), `exauser` (Exa fetching for an agent), a VS Code Electron UA (`Code/x ... Electron/y`, Copilot's fetch). Checked before AI bots because Claude Code's UA also contains `Claude-User`.
3. AI provider bot tokens (table above), case-insensitive substring.
4. If the log has an Accept header: `text/markdown` from a non-bot is a coding agent (`text/markdown, text/html, */*` with a generic UA is Claude Code's WebFetch). Browsers never ask for markdown.
5. CLI and library clients (`curl/`, `wget/`, `python-requests/`, `httpx`, `node`, `undici`, `axios/`, `go-http-client/`, `bun/`, `deno/`, `colly`, `got (`) on docs paths (`/docs`, `/reference`, `/api-reference`, `/guides`, `/quickstart`, `/sdk`, `.md`, `llms.txt`, or a `docs.` host): unnamed coding agent. Elsewhere: script (other-bot).
6. Named search engines, SEO tools, previews and monitors; then any `...bot`, `...crawler`, `...spider` token: other-bot.
7. Not browser-shaped (does not start with `Mozilla/` plus an engine): other-bot.
8. Everything else: human. Some agents copy a full Chrome UA (OpenCode, Kilo Code and headless agents); without Accept headers or TLS fingerprints they land here, so coding-agent counts are a floor.

Assets (JS, CSS, images, fonts, `/_next/static`, `?_rsc=` prefetches, health and monitoring routes) are dropped before counting. robots.txt, sitemaps, llms.txt, `.md` and OpenAPI files are kept and reported separately.

## 3. Verification and spoofing

- Declared: the user agent names the agent. Verified: the IP is in the provider's published list or passes reverse-then-forward DNS.
- `--verify-ips` downloads: openai.com/gptbot.json, searchbot.json, chatgpt-user.json; claude.com/crawling/bots.json; perplexity.ai/perplexitybot.json and perplexity-user.json; Google common-crawlers, user-triggered-agents and user-triggered-fetchers lists; bing.com/toolbox/bingbot.json. Results per agent: verified, not in list (likely spoofed or a list gap), list unavailable, user machine (Claude Code), no list.
- Reverse DNS works for Googlebot (googlebot.com, google.com), Bingbot (search.msn.com) and Applebot (applebot.apple.com); do it for a handful of IPs by hand (`host <ip>` then `host <hostname>`).
- Scanner heuristic: an AI user agent requesting `/.env`, `/wp-login.php`, `/.git/`, `/xmlrpc.php`, `/actuator` and similar is reclassified as other-bot ("scanner claiming GPTBot").
- Cloud coding agents (Codex cloud, Cursor background agents) and Anthropic API tool calls often fetch with plain curl from the provider's published egress ranges. The analyzer does not check those ranges, so they count as unnamed coding agents on docs and as scripts elsewhere.

## 4. AI referrals from people

Counted on human visits only. Referrer hosts: chatgpt.com, chat.openai.com, perplexity.ai, claude.ai, gemini.google.com, copilot.microsoft.com, meta.ai, grok.com, deepseek.com, chat.mistral.ai, poe.com, phind.com, you.com, kagi.com. Also `utm_source=chatgpt.com` (and similar values) on the landing URL. Treat the total as a floor.

## 5. Adding an agent

If the report shows an unknown name with real volume, look at a few raw lines (`grep -i '<name>' access.log | head`), check the vendor's bot documentation, and either tell the user what it is or add its token to the lists at the top of `scripts/analyze_logs.py` (CODING_AGENT_TOKENS, AI_BOTS or OTHER_BOTS) and rerun.
