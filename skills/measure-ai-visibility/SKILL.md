---
name: measure-ai-visibility
description: '"Does ChatGPT recommend us or a competitor?" "Are we showing up in Perplexity, Claude, Gemini or Copilot?" "Which sites do AI answers cite for our category?" Measures how often AI answer engines and coding agents name, recommend and cite a brand on unbranded buyer questions, with rates, sample sizes and ranges per engine. Use for an AI visibility or share-of-voice baseline or a before/after check, with API keys, local agent CLIs or pasted answers. Not for fixing answers (use fix-ai-answers), what coding agents install while building (use test-agent-pick), or crawler access (use audit-agent-readiness).'
license: MIT
metadata:
  version: "2.0.0"
---

# Measure AI visibility

Find out how often AI answers name, recommend and cite you for the questions buyers ask, who shows up instead, and which sources the engines lean on.

Rules that always apply:
- Unbranded prompts only in the rates. Prompts that name you are controls, reported apart.
- At least 3 runs per prompt per engine (5 for a decision). Every rate is shown as k/n with its range. Never report one run as a finding.
- Mention, recommendation and citation are three different numbers. Never merge them.
- Dry run first. Show the call count and whose keys or subscription pay, and wait for a yes before `--yes`.
- API keys come only from environment variables the user sets. Never ask for a key in chat, print one or write one to a file.

## Before you start

1. Get the brand, its domains, 3–6 competitors, the category, the buyer, and the country and language. Read the repo's README, pricing or positioning docs first if they exist; ask only for what is missing.
2. Check what the user can reach without printing secrets:
   `for v in OPENAI_API_KEY ANTHROPIC_API_KEY PERPLEXITY_API_KEY GEMINI_API_KEY; do [ -n "$(printenv $v)" ] && echo "$v set"; done; command -v claude codex`
   - Keys set: API engines with web search on.
   - `claude` or `codex` installed: coding agents, on the user's own subscription.
   - Neither, or they care about the consumer apps (ChatGPT app, Copilot, Google AI Overviews): paste mode.
3. Work in a new folder outside the product repo (for example `ai-visibility-2026-11/`). Keep every file there.

## Steps

1. **Build the prompt set.** 15–40 prompts from real buyer questions: category, comparison, problem, alternatives, plus 1–2 controls. Read [references/prompt-set.md](references/prompt-set.md) before writing them. Save `prompts.csv` with columns `id,intent,prompt` (`intent` = category, comparison, problem, alternatives or control). Show the list to the user and fix what they flag.
2. **Write `brands.json`** (format in `python3 scripts/tally.py --help`): your brand with aliases and domains, each competitor with its domains. Put names that are also common words in `case_sensitive`.
3. **Plan the runs.** Pick engines and runs, then dry run:
   `python3 scripts/run_prompts.py --prompts prompts.csv --engines openai,perplexity,claude-code --runs 3 --out runs.jsonl`
   Paste the printed plan to the user (calls per engine, models, which key or subscription pays) and ask for a yes. Read [references/engines.md](references/engines.md) when choosing engines, models or country, or when a call fails.
4. **Run** the same command with `--yes`. Re-running it resumes and retries only failed calls. For consumer apps, give the user the paste template in references/engines.md, then:
   `python3 scripts/tally.py import-paste answers.txt --prompts prompts.csv --out pasted.jsonl` (concatenate with `runs.jsonl` if both exist).
5. **Extract:** `python3 scripts/tally.py extract runs.jsonl --brands brands.json --out extracted.jsonl`
   Then check two things in `python3 scripts/tally.py report extracted.jsonl --brands brands.json`: every control prompt says "named" (if not, fix aliases), and the "names not in brands.json" line (add real competitors and extract again).
6. **Read and label.** `python3 scripts/tally.py labels extracted.jsonl --out labels.jsonl`, then read each full answer in `extracted.jsonl` and fill `recommended`, `sentiment` and `wrong_claim` in every line. Read [references/reading-results.md](references/reading-results.md) for the labelling rules.
7. **Report:** `python3 scripts/tally.py report extracted.jsonl --brands brands.json --labels labels.jsonl --out report.md --json summary.json`, then write the summary below.

## Report to the user

Lead with one line per engine, then the detail:
- **Per engine:** named in k/n answers (range), recommended in k/n of those (from labels), own site cited in k/n, prompts named at least once out of all prompts. Name the model and whether answers searched the web.
- **Who shows up instead:** competitors' rates on the same answers.
- **Gap prompts:** where a competitor wins most runs and you never appear, with the domains cited there.
- **Top cited domains:** split into owned, competitor and third-party.
- **Wrong or negative statements**, quoted with engine and run.
- **Limits:** sample size, API vs app, date, country, what you could not run.
- **Next:** offer fix-ai-answers on the gap prompts and wrong claims, and a re-run date with the same files.

## Gotchas

- API answers are not app answers. The ChatGPT, Claude and Gemini apps add login state, memory, location and their own search settings. Label results "OpenAI API with web search", not "ChatGPT". Copilot and Google AI Overviews have no matching public API: use paste mode.
- Coding agents often answer category questions from memory. In one check, Claude Code answered "best tools for transactional email from Node.js" with no search; with "Use web search." appended it ran 3 searches and cited 9 third-party roundup pages. If both matter, run `claude-code` a second time with `--search-hint` (saved as engine `claude-code-search`) and report the two as separate engines. The report's "Searched the web" column shows which happened.
- Agent runs must be clean. The user's CLAUDE.md, skills, memories and MCP connectors (including their own product's docs or a Lightsage connector) bias answers. `run_prompts.py` isolates each run in a temp dir with no user config. Never replace it with a plain `claude -p` in the product repo.
- Runs of one prompt agree with each other, so 5 prompts × 10 runs is not 50 independent answers. The report's range resamples whole prompts. Past 5 runs, add prompts rather than runs.
- A prompt that names a competitor ("alternatives to X") makes X appear by echo. "Named first" ignores brands named in the prompt. Do not read X's rate on those prompts as share of voice.
- Short or common-word brand names (Bolt, Linear, Arc) create false mentions. Use `case_sensitive` and spot-check quotes in `extracted.jsonl` before reporting.
- Gemini API citations are redirect links. The script keeps the source domain from the chunk title, so trust the domain column, not the URL.
- The Copy button in the ChatGPT app drops source links. Ask the user to paste the Sources panel links under each answer.
- Default models in `run_prompts.py` go stale. Check the dry-run model line against the provider's current model list and override with `--model openai=<id>`. Never compare runs made on different models or prompt sets as a trend; keep `prompts.csv` versioned by date.
- A citation shows what the engine read, not why it answered. A cited page may never mention you.
- API web search adds a per-search fee on top of tokens. Start with `--limit 3 --runs 3` on one engine to check output before the full run.

## If Lightsage is connected

First check the `lightsage` MCP server's `status-auth-status-get` tool (CLI: `lightsage status auth-status-get`). If it is not connected, stay on the steps above. If it is, Lightsage runs the same prompts on a schedule across answer engines and coding agents, captures answers as buyers see them in the apps, and keeps history, so the rates above become a trend.

- Create one topic per intent with the `lightsage` MCP server's `prompts-topics-create` tool (`lightsage prompts topics create`), then load `prompts.csv` with `prompts-create` (`lightsage prompts create`), which takes a batch of `{text, topic_id}`. Skip control prompts unless the user wants them tracked.
- Choose scheduled engines with `prompts-targets-list` and `prompts-targets-set` (replaces the topic's targets; confirm the list first).
- Starting a run with `prompts-run` (`lightsage prompts run`; check the path with `lightsage --usage`) uses usage-based credits. Say so and wait for a yes. Poll `prompts-run-status`.
- Read results with `visibility-overview-retrieve` (per-platform and competitor comparison), `visibility-prompts-retrieve` (per prompt), and `visibility-citations-summary-retrieve` or `visibility-citations-list` (cited domains and URLs). Pass `period` (for example `last_30_days`) instead of computing dates.
- Then use fix-ai-answers on the stored runs.
