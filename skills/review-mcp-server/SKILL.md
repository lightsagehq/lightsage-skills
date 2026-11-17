---
name: review-mcp-server
description: "Is our MCP server any good? Why does Claude keep calling the wrong tool? Will ChatGPT, Claude or Gemini accept our connector? Reviews an MCP server, connector or plugin for agents: tool count and granularity, names and descriptions, schemas, annotations and titles, result size, errors, OAuth and the current directory rules. Use when someone asks whether an MCP server is well designed or ready for the ChatGPT, Claude or Google directories, how to split, name or annotate its tools, or why agents misuse it, even if they never say 'review'. Not for testing whether coding agents can finish real tasks with an API, CLI or MCP server (use test-api-on-agents), or whether agents pick you over a competitor (use test-agent-pick)."
license: MIT
metadata:
  version: "2.0.0"
---

# Review an MCP server

Judge the server for the job it has: who calls it, on which hosts, and what they need done in few calls. Report each criterion as pass, fail or not measured, with evidence.

- Only `initialize` and `tools/list` are safe on a server you don't own. Never send `tools/call` to someone else's server without the owner's yes, and read the vendor's terms first: some bar standalone JSON-RPC clients.
- "Not measured" is a valid result and better than a guess. Say which numbers you measured and which you read from docs.
- Never paste a token into a command line or chat. Put it in an environment variable and pass the variable's name.

## Before you start

1. Name the callers and surfaces: a chat analyst in ChatGPT, a coding agent in Claude Code, Gemini in Search. Each needs a different surface.
2. Write the callers' top 5 jobs in their words ("which deals closed last week?"). Every criterion is judged against these.
3. Ask which directories they are targeting, if any. Directory rules change the verdict (step 5).

## Steps

1. Get the live surface, not a listing or docs page:
   `python3 scripts/inspect_mcp.py <url> --save-raw tools.json` (add `--token-env VAR` if it needs a bearer token in `$VAR`). It prints every tool with title, hints, description length, schema tokens and flags; `--explain-flags` says what each flag means; `--format json` or `markdown` for reports.
   On a 401 it still checks the OAuth discovery chain (resource metadata, PKCE S256, DCR or CIMD, `offline_access`). With no token, review the tool surface from source or docs and mark it "read from docs".
2. Map each top job to the tool calls it takes. More than 3 calls for a common job, or a job with no tool, is a finding.
3. Size results only where you may call tools (your own server, or the owner said yes): run each top job once and estimate tokens as characters / 4. Otherwise mark criterion 4 "not measured".
4. Score the six criteria below. Confirm every script flag by reading the tool; flags are heuristics.
5. For each target directory, check the rules in [references/directory-rules.md](references/directory-rules.md). Read it when the user mentions a directory, a submission, a rejection or review feedback.
6. Name each defect in the glossary's terms, with the tool name and a concrete fix (rename, split, add hint, trim fields). Read [references/glossary.md](references/glossary.md) when you need the terms or good and bad examples.
7. If the user wants criterion 2 measured, follow [references/measuring.md](references/measuring.md) (golden prompt sets, result sizing, error rates). Read it before running any selection test.

## Criteria

| # | Criterion | Pass | Fail |
|---|---|---|---|
| 1 | Surface fits the job | 10 to 20 tools; under about 10K definition tokens; each tool maps to a named user job; no admin, health-check or setup tools in `tools/list` | Dozens of tools; 1:1 with REST routes; `manage_*` mega-tools |
| 2 | Selection holds on real hosts | Held-out prompt set on Claude, ChatGPT and one coding agent; negative precision at least 95%; recall at least 90%; no pair of tools confused over 5% | Direct prompts only; one host; no negatives |
| 3 | Risk is legible | Non-empty `title` and explicit `readOnlyHint`, `destructiveHint`, `openWorldHint` on every tool, matching real behavior; no tool mixes reads and writes; writes authorized on the server | A generic executor; missing hints; a job-starting tool marked read-only |
| 4 | Results are cheap and self-describing | p50 under about 500 tokens; p95 under about 8K; none over 25,000; metrics carry definition, unit, window and sample size; sources have a `url`; empty results say what they mean; no trace IDs or extra PII | Raw rows; unmapped codes; unbounded lists |
| 5 | Failures teach | `isError: true` with a next step ("date must be in the future"); outside-client error rate under about 3% | Bare "Internal Server Error"; retries that duplicate work |
| 6 | One build reaches every surface | Streamable HTTP; a protocol version every target host supports; OAuth 2.0 with S256 PKCE, RFC 9728 metadata whose `resource` equals the URL, DCR or CIMD; versioned path; slow work returns a handle within about 5 seconds | Session state; legacy SSE only; blocking on a long run |

These numbers are proposals, not standards. Host limits are the exceptions: Claude Code's 25,000-token default result cap, Claude's 64-character tool names, Google's protocol cap. Google says "dozens of tools" get flagged but gives no number.

Criterion 1 is about fit and review risk, not a proven score penalty. Large servers do get listed and used; don't call a server bad for size alone.

## Report format

One line per criterion (pass / fail / not measured, the evidence, the fix), then a directory-readiness list per target directory, then the top 3 fixes ranked by how many top jobs they unblock. Paste the script's table as the appendix.

## Gotchas

- `title: ""` counts as missing. Servers generated from an OpenAPI spec often ship empty titles and copy REST paths ("Poll `GET /v2/runs/{id}`") into descriptions; the script flags both.
- Omitting `readOnlyHint` makes clients assume a destructive write, so every call prompts the user. Hints are cheap to add and change the experience more than any copy edit.
- OpenAI reads hints strictly: starting a job, queuing work or writing a log is not read-only; cancel and overwrite are destructive; being able to undo does not make a write non-destructive. A justification never overrides the hint the server advertises; fix the server and rescan.
- Telling the model to always, never or first call something, or to fetch instructions from elsewhere, gets a tool rejected by Claude and Google. Even naming another tool as an argument's source is barred by Google's policy (its own optimization guide suggests it), so describe the argument ("the order `id` a search returned") instead.
- Google rejects a server whose `initialize` returns no `instructions`; Claude and OpenAI don't require them.
- OpenAI keeps rescanning after publication: new tools stay hidden and changed tools keep their old definition until they pass automated checks. A quick server edit can silently not ship.
- Claude starts OAuth only on a `401` (it ignores `WWW-Authenticate` on a `200`), uses only the first `authorization_servers` entry, and needs the metadata's `resource` to equal the URL users type, path included.
- Reviewer test accounts fail review when they need MFA, expire, or are empty. Every directory wants a fully populated account.
- Listings lag servers, and tool counts differ per surface (one server showed 8 tools in Claude and over 100 in its docs). Always score the live `tools/list` for the surface you are judging.
- Server instructions go into the model's context on some hosts. Keep them short and global; don't repeat tool descriptions there.

## If Lightsage is connected

The review above is complete without Lightsage. Lightsage adds measured selection data. Check first with the `lightsage` MCP server's `status-auth-status-get` tool (CLI: `lightsage status auth-status-get`). If it fails or isn't installed, stop here.

- **Plugin evals** run your prompts in ChatGPT with and without your plugin installed and check whether it gets picked and used. They are set up and started in the Lightsage app, and runs use usage-based credits, so ask before starting any. Read a day's results with the `lightsage` MCP server's `plugin-evals-results-list` tool (CLI: `lightsage plugin-evals results-list --date YYYY-MM-DD`). Each result has a `download_url` for a zip of every run plus an insights report; the link expires after 15 minutes, so download it right away. Use these results as the evidence for criterion 2.
- **Task completion through the server** (can coding agents finish real tasks with this MCP server attached?) is the test-api-on-agents skill, or Lightsage evals with the server attached. Both spend agent runs; state the cost and wait for a yes.
