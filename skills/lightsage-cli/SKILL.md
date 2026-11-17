---
name: lightsage-cli
description: "\"List my Lightsage prompts from the shell\", \"kick off a Lightsage eval in our GitHub Action\", \"script a weekly export of our visibility numbers\", \"lightsage: command not found\", \"auth keeps failing in CI\". Runs the `lightsage` CLI for Lightsage workspaces. Use when someone wants a terminal command, shell script, cron job or CI step that reads or changes Lightsage prompts, prompt runs, evals, tasks, visibility, agent analytics, site audits or plugin eval results, or needs to install, authenticate or debug the CLI. Not for deciding what prompt-run or eval results mean or what to fix (use fix-ai-answers or fix-failed-evals), and not for work done through the connected Lightsage MCP server in chat."
license: MIT
metadata:
  version: "2.0.0"
---

# Lightsage CLI

Carry out the user's Lightsage task with the installed `lightsage` binary, accurately and safely. This skill is CLI mechanics; outcome reasoning lives in the workflow skills.

- The installed binary is the authority for command names and flags. Docs and older examples can lag it.
- Never print, paste or pass an API key on the command line. Use `lightsage auth login` locally or the `LIGHTSAGE_API_KEY` environment variable from a secret store in CI.
- `lightsage prompts run` and `lightsage evals run` (including Agent Preference evals) use usage-based credits. Before running one, say what it fans out to (prompts x targets, or prompts x agents x runs) and that it uses usage-based credits, then wait for a yes. Never describe pricing beyond that.
- Never retry a write whose outcome is uncertain, and never turn "archive" or "remove from this config" into a permanent delete.

## Before you start

1. `lightsage version`. If the command is missing, ask before installing, then `brew install lightsagehq/tools/lightsage` (macOS and Linux). Don't use an installer URL you haven't verified.
2. `lightsage auth whoami` shows where credentials come from (`[env]`, `[keyring]`, `[config]`) with values masked. Then `lightsage status auth-status-get --no-interactive` validates the key and returns its organization and scopes. `lightsage status get` only checks that the API is up.
3. No key or no workspace: follow "Without a Lightsage workspace" below.

## Steps

1. **Find the command.** `lightsage --usage` prints the whole tree as KDL (commands, flags, defaults, env vars). Then `lightsage <group> <command> --help` for one command. These work without credentials.
2. **Resolve IDs.** IDs are opaque: list, match on stable fields (name, URL, status), retrieve when identity matters. If several match, ask. If the list is empty, report the missing prerequisite; never invent an ID.
3. **Preview writes.** `--dry-run` prints the exact request to stderr and ends with `[DRY-RUN] Network call skipped.`. `--schema` prints the JSON Schema for commands that take `--body`. Summarize the method, path and body for the user.
4. **Execute** when the preview matches the request (after the credit yes, for runs). Use long command names, `--no-interactive` in scripts, and `--output-format json` before any `--jq`.
5. **Verify and report.** Retrieve the changed resource or poll the run, then state what was inspected or changed, the resource ID and how you verified it. An exit code or a dry run is not proof.

Read [references/resource-model.md](references/resource-model.md) when choosing a command for a resource or following IDs between resources. Read [references/command-patterns.md](references/command-patterns.md) for verified examples of discovery, JSON output, repeated flags, dry runs and polling. Read [references/safety-and-recovery.md](references/safety-and-recovery.md) when a write may not match the user's intent, or when auth, empty catalogs, validation or service errors block the task.

## Command groups (CLI 0.11.24, 2026-11-17)

| Group | What it covers |
|---|---|
| `auth login / whoami / logout`, `whoami`, `configure` | Credentials and saved settings |
| `status get / auth-status-get` | API liveness; key validation |
| `prompts list / create / retrieve / update / delete`, `prompts topics ...`, `prompts targets-list / targets-set` | Tracked prompts, topics and scheduled targets |
| `prompts run / run-status / run-cancel`, `prompts runs list / retrieve` | Start, poll and read prompt runs |
| `visibility current-retrieve / overview-retrieve / prompts-retrieve / citations-list / citations-summary-retrieve` | Visibility scores and citations |
| `opportunities list / retrieve`, `tasks list / create / retrieve / update` | Ranked opportunities and the task queue |
| `evals list / create / retrieve / update / delete / batch-create`, `evals configurations ...`, `eval-templates ...` | Eval definitions and saved runtimes |
| `evals run / get / monitor / trace / cancel`, `eval-runs list` | Start and follow eval runs |
| `agent-preference evals ...`, `agent-preference competitors list`, `agent-preference head-to-head retrieve` | Head-to-head pick evals |
| `agents / environments / mcp-servers / clis / skills list`, `repositories ...` | Catalogs for eval runs |
| `site-audits list / retrieve`, `agent-analytics sites-list / summary-retrieve / pages-list / sources-list / countries-list / error-pages-list` | Existing audit results; agent and bot traffic |
| `plugin-evals results-list / results-download` | Plugin eval results for a day |

## Gotchas

- Inside Claude Code, Cursor and other detected agent environments the CLI turns on agent mode: structured errors and TOON output by default. Pass `--output-format json` whenever you parse output or use `--jq`.
- Generated docs and some READMEs show `v2-` names (`lightsage prompts v2-prompts-list`). The shipped binary uses short names (`lightsage prompts list`). Follow `--usage`.
- `lightsage prompts run` with no `--prompt-ids` runs every active prompt on every configured target. Pass IDs unless the user asked for all, and confirm the size.
- `evals run` fans out prompts x agents x runs; a persona doesn't multiply attempts. It fails with `402` before dispatch if credits are short, and `400` if an environment holds an empty or placeholder secret.
- Progress can reach 100 percent before a run's status is terminal. Poll `evals get <run-id>` or `prompts run-status <run-id>` until the status is terminal. There is no separate eval-results command: `evals get` returns results and analysis once attempts finish.
- Agent Preference evals don't appear in `evals list`; list them with `agent-preference evals list` and start them with `evals run --eval-id <id>`.
- List flags repeat once per value (`--agent <id> --agent <id>` with IDs from `agents list`; also `--judge`, `--prompt`, `--cli`, `--mcp`). Don't pass a JSON array string; check the dry-run body.
- `agents`, `environments`, `mcp-servers`, `clis` and `skills` are list-only. An empty catalog means setup is needed in the Lightsage app; don't invent a create command.
- `site-audits` and `agent-analytics` read existing data; they never start a crawl.
- A plugin eval `download_url` works without a key for 15 minutes. Download it right away (`curl -o results.zip "<download_url>"`) or use `plugin-evals results-download --output-file`.
- `auth login` is interactive and stores the key in the OS keychain. In CI, set `LIGHTSAGE_API_KEY` from the secret store and add `--no-interactive`.

## Without a Lightsage workspace

Everything except `--help`, `--usage`, `--schema`, `--dry-run` and `status get` needs an API key from a Lightsage workspace.

- To get one: sign up at https://app.lightsage.com, then create a key under Settings > API Keys. Keys are shown once; store them in a secret manager, never in the repo.
- Until then, the open skills do the same jobs locally: measure-ai-visibility (instead of prompt runs and visibility), test-agent-pick (instead of Agent Preference evals), test-api-on-agents (instead of evals), audit-agent-readiness (instead of site audits), read-agent-traffic (instead of agent analytics), review-mcp-server (instead of plugin evals).
