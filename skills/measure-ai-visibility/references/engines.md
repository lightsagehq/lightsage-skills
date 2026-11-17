# Engines: setup, what each one measures, paste mode

## Contents
- API engines
- Coding agents
- Paste mode for consumer apps
- Choosing engines
- When a call fails

## API engines

The user sets the key in their own shell (`export OPENAI_API_KEY=...`) before you run anything. Never ask for the key in chat.

| `--engines` | Key variable | Default model, checked 2026-11-17 (model IDs change often: override with `--model engine=id`) | Web search | Country |
|---|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | `gpt-6-astra` | Responses API `web_search` tool | `--country` sets approximate location |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-opus-5-5` | `web_search` server tool, up to 5 searches | `--country` |
| `perplexity` | `PERPLEXITY_API_KEY` | `sonar` | always on | `--country` |
| `gemini` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `gemini-4-hydrogen` | `google_search` grounding | not supported |

- Defaults go stale. Before the run, check the provider's model list and pick the model closest to what their consumer app serves today; the dry run prints the model so the user can confirm.
- What it measures: the model plus that provider's API search tool. Close to the app for Perplexity; further from the app for ChatGPT (the app adds memory, personalization and its own search pipeline) and Gemini (the app is not the API).
- Cost: tokens plus a per-search fee. Prefer a cheaper model for a first pass only if the user accepts that it differs from the app model.
- `searched` comes from the API's search events; `sources_seen` lists pages the engine retrieved (OpenAI, Anthropic, Perplexity), which can be more than it cited.

## Coding agents

| `--engines` | Needs | What the script does |
|---|---|---|
| `claude-code` | `claude` CLI logged in | Fresh temp dir per run; `--setting-sources ""`, `--strict-mcp-config`, `--disable-slash-commands`, `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`; only WebSearch and WebFetch tools; no session saved |
| `codex` | `codex` CLI logged in | Temp `HOME` and `CODEX_HOME` with only the auth file linked, so no config, AGENTS.md, skills, MCP servers or memories; apps and plugins disabled; read-only sandbox; live web search; stdin closed |

- These runs use the user's own subscription. The dry run says how many sessions; get a yes.
- Pass `--claude-bin` or `--codex-bin` if the CLI on PATH is a wrapper.
- `--model claude-code=<id>` or `--model codex=<id>` pins a model. Without it the agent's default is used; Claude Code reports the model, Codex records "codex default".
- `--search-hint` appends "Use web search." and saves those answers as engine `claude-code-search` or `codex-search`, so both arms can share one `--out` file and show as separate rows in the report.
- Citations for agents are the URLs in the final answer. Claude Code also records every URL its tools fetched in `sources_seen`.
- Do not use `--bare` for Claude Code: it cannot use a subscription login.
- Agents take 10–60 seconds per answer. Keep `--workers` at 2–3 so local rate limits do not turn into errors.

## Paste mode for consumer apps

Use it for the ChatGPT app, Copilot, Google AI Overviews or AI Mode, the Gemini app, the Claude app, or when the user has no keys. Give the user this template and ask them to run each prompt 3 times, each in a new chat (or a temporary chat), and to note whether they were logged in:

```
=== engine: chatgpt-app | run: 1 | prompt: <prompt text exactly as in prompts.csv> | logged_in: no | date: 2026-11-17
<paste the whole answer>
Sources: <paste the links from the Sources panel, one per line or space separated>

=== engine: chatgpt-app | run: 2 | prompt: <same prompt>
...
```

Rules for clean pasted data:
- A new chat for every run. A follow-up in the same chat is not a new run.
- Same account state for every run (all logged out, or all in one account with memory off).
- Engine names stay consistent (`chatgpt-app`, `copilot`, `google-ai-overview`, `gemini-app`, `claude-app`, `perplexity-app`).
- ChatGPT's Copy button drops links. Copy the Sources panel too, or the citation columns will be empty for that engine.
- AI Overviews do not show for every query. Record "no AI Overview" as its own line (`=== engine: google-ai-overview | run: 1 | prompt: ...` followed by `NO AI OVERVIEW`) and tell the user those answers count as "not named".

Then `python3 scripts/tally.py import-paste answers.txt --prompts prompts.csv --out pasted.jsonl` matches each block to its prompt id by text.

## Choosing engines

- A marketer asking "are we in ChatGPT?": paste mode on the ChatGPT app is the honest answer; add `openai` for scale and say which is which.
- A devtool asking whether developers get pointed to them: `claude-code` and `codex`, with and without the search hint, plus `perplexity` or `openai`.
- A quick baseline with no keys: paste mode on 15 prompts × 3 runs on one app is 45 pastes, about an hour of the user's time. Say so before they start.

## When a call fails

- Errors are saved with the reason and excluded from rates. Re-run the same command to retry only those.
- HTTP 401/403: wrong or missing key, or the model is not enabled for that key.
- HTTP 404 or "model not found": the default model was retired; pass `--model`.
- HTTP 429: lower `--workers`; the script already backs off and retries 3 times.
- `claude exit` or `codex exit` with a login message: the user must log in to that CLI themselves.
- If more than 10% of calls on one engine fail, report that engine as incomplete instead of reporting its rate.
