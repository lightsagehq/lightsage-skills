# AI user agents: what each one is for

Read when the user asks which bot does what, which robots.txt token to use, or how to tell a real bot from a spoofed one. Checked November 2026; providers add agents often, so confirm against their docs before a policy change.

Contents
1. Three purposes per provider
2. Token table
3. Coding agents
4. Verifying a bot is real

## 1. Three purposes per provider

- Training crawler: collects pages for future models. Blocking it changes what models know from memory; it does not change live answers or citations.
- Search indexer: builds the index an assistant searches before answering. Blocking it removes pages from that assistant's search results and citations.
- User-triggered fetcher: opens a page because a person asked (pasted a URL, or the assistant chose to read a result). Blocking it means the assistant answers from snippets or a competitor's page. OpenAI and Perplexity say robots.txt may not apply to these fetches; a WAF rule still blocks them.

## 2. Token table

| Token (robots.txt and UA) | Provider | Purpose | Notes |
|---|---|---|---|
| OAI-SearchBot | OpenAI | search | ChatGPT search results and citations |
| ChatGPT-User | OpenAI | user | ChatGPT opening pages for a user; also used by custom GPT actions |
| OAI-Operator | OpenAI | user | ChatGPT agent browsing |
| GPTBot | OpenAI | training | |
| Claude-SearchBot | Anthropic | search | |
| Claude-User | Anthropic | user | Claude apps fetching for a user; Claude Code's WebFetch sends `Claude-User (claude-code/<version>; ...)` |
| ClaudeBot | Anthropic | training | |
| PerplexityBot | Perplexity | search | |
| Perplexity-User | Perplexity | user | |
| Googlebot | Google | search | Google Search, AI Overviews and AI Mode all use Googlebot's crawl |
| Google-Extended | Google | policy token | Controls Gemini training and grounding use; never sent as a UA; no effect on Search |
| Google-Agent, Gemini-Deep-Research, Google-NotebookLM | Google | user | User-triggered Google agents |
| Bingbot | Microsoft | search | Bing and Copilot; other AI search products license Bing results |
| Applebot | Apple | search | Siri and Spotlight |
| Applebot-Extended | Apple | policy token | Apple AI training; never sent as a UA |
| meta-externalagent | Meta | training | |
| meta-externalfetcher | Meta | user | |
| CCBot | Common Crawl | training | Used by many model builders |
| Bytespider | ByteDance | training | |
| DuckAssistBot | DuckDuckGo | search | AI answers |
| MistralAI-User | Mistral | user | |
| Amazonbot | Amazon | search/other | Alexa and Amazon products |

## 3. Coding agents

Coding agents rarely name themselves the way crawlers do:
- Claude Code: `Claude-User (claude-code/...)`, `Accept: text/markdown, text/html, */*`.
- Codex, Gemini CLI and most shells: `curl/<version>` or a language HTTP client (python-requests, node, undici) with `Accept: */*`.
- OpenCode and Kilo Code: a Chrome-like UA with a q-weighted Accept list that prefers markdown.
- VS Code Copilot's fetch: an Electron UA (`Code/<version> ... Electron/...`).
- Gemini CLI web fetch: `google-gemini-cli`; Gemini URL context: `GoogleAgent-URLContext`.
So: never block bare `curl` or generic HTTP clients on docs paths, and test docs with both `curl` and `Claude-User`.

## 4. Verifying a bot is real

A user-agent string is a claim. To verify, check the request IP against the provider's published list, or reverse-then-forward DNS:

| Agent | Method |
|---|---|
| GPTBot, OAI-SearchBot, ChatGPT-User | IP lists: openai.com/gptbot.json, openai.com/searchbot.json, openai.com/chatgpt-user.json |
| ClaudeBot, Claude-User, Claude-SearchBot | IP list: claude.com/crawling/bots.json |
| PerplexityBot, Perplexity-User | IP lists: perplexity.ai/perplexitybot.json, perplexity.ai/perplexity-user.json |
| Googlebot | IP list developers.google.com/static/crawling/ipranges/common-crawlers.json, or reverse DNS ending in googlebot.com / google.com |
| Google user-triggered agents | developers.google.com/static/crawling/ipranges/user-triggered-agents.json and user-triggered-fetchers-google.json |
| Bingbot | IP list bing.com/toolbox/bingbot.json, or reverse DNS ending in search.msn.com |
| Applebot | reverse DNS ending in applebot.apple.com |

Forward-confirm reverse DNS (the hostname must resolve back to the same IP). Allowlisting by verified identity is better than by user agent: spoofers wear AI user agents to get past bot rules.
