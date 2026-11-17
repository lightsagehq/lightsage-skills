---
name: track-agent-pick
description: '"Are we winning against Stripe on coding agents this week?" "Did Codex start recommending our competitor?" "Set up a head-to-head of us vs X on Claude Code, Codex and Cursor." Sets up, runs and reads Lightsage Agent Preference evals for Lightsage workspaces - head-to-head win, loss and tie records against tracked competitors across many hosted coding agents, with week-over-week change and the reasons behind losses. Use when the user wants agent recommendation share tracked over time, compared per agent, or checked after a docs change, and a Lightsage workspace is connected. Not for a one-off local test without an account (use test-agent-pick), task pass rates for an API or MCP server (use fix-failed-evals), or answer-engine visibility from prompt runs (use fix-ai-answers).'
license: MIT
metadata:
  version: "2.0.0"
---

# Track agent pick

Keep a running head-to-head of how often coding agents recommend the user's company over each
competitor, per agent, and explain the losses.

Rules that hold every time:

- **Confirm before spending.** Starting a run uses usage-based credits. State the attempt count
  (prompts x agents x runs) and wait for a yes. Confirm before creating, changing or deleting an
  eval too; deletion is permanent.
- **Every rate with n.** "Won 14 of 36 (39%)", never "39%". Report ties and no-result attempts
  separately; no-result attempts (errors) are never losses.
- **Compare like with like.** Same eval, prompts, agent IDs and settings on both sides of any
  week-over-week or before-and-after claim.
- **Fixes are tests.** Every page change you suggest comes with the rerun that would show it worked.

## Before you start

1. Check the connection: the `lightsage` MCP server's `status-auth-status-get` tool (CLI:
   `lightsage status auth-status-get`). No workspace or no auth: go to "Without a Lightsage
   workspace" below.
2. List what exists before creating anything: `agent-preference-evals-list` (CLI:
   `lightsage agent-preference evals list`). Agent Preference evals do not appear in `evals-list`.
3. If you will create or change an eval: `agent-preference-competitors-list` for tracked
   competitors and `agents-list` for runnable agent IDs (CLI: `lightsage agent-preference
   competitors list`, `lightsage agents list`). Check CLI command names with `lightsage --usage`.

## Steps

**Set up** (skip when a suitable eval exists). Read [references/setup.md](references/setup.md)
before creating or editing an eval.

1. One eval per competitor. The competitor must already be tracked; if it is missing, tell the
   user to add it in the Lightsage app rather than guessing an ID.
2. Draft up to 20 unbranded prompts (buying questions and build tasks), the agents, runs (3 or
   more), and a starting repository for build tasks. Show it as a table with the attempt count
   per run, get a yes, then call `agent-preference-evals-create`. Creating does not start a run.

**Run**

3. State "This run makes N attempts (P prompts x A agents x R runs) and uses usage-based
   credits." Wait for a yes. Then call `evals-run` with the eval's `id` as `eval_id` (CLI:
   `lightsage evals run`). A refusal for insufficient credits means stop and tell the user.
4. Poll `evals-get` with the run ID until `status` is `completed`, `failed` or `cancelled`.
   Progress can reach 100% before the status is final.

**Read.** Read [references/reading-results.md](references/reading-results.md) before reporting.

5. Save to files: every page of `agent-preference-evals-results-list` (limit up to 200, page
   with `offset`), `evals-get` for the runs you are reading (adds prompts, agent versions,
   analysis and tool calls), and `agent-preference-evals-list` (names). Then run
   `python3 scripts/summarize.py <files> --period week` (add `--split DATE` around a change).
6. For the cross-competitor overview, `agent-preference-head-to-head-retrieve` (limit up to
   500). It reads the most recent attempts across all evals; if `truncated` is true, say so.
7. Read the losing attempts: each lost or tied result's `analysis` and `tool_calls` in
   `evals-get`, and `evals-trace` when you need what the agent searched and fetched. Give each
   loss a reason in the agent's words and a loss code.
8. Report (format below), then propose 1 to 3 page changes framed as tests.

## Report format

1. **Answer first**: "This week you won 14 of 36 head-to-heads against Competitor A (39%,
   25-55%), up from 9 of 36; ties 5, no result 1."
2. **Per agent**: won, lost, tied, n and win rate for each agent ID, with its version.
3. **What changed vs last period**: per agent, the change and its p-value from `summarize.py`.
   With fewer than about 30 comparisons a side, call changes directional.
4. **Why you lose**: top reasons with counts and the prompts they come from; what agents read.
5. **What to test**: 1 to 3 changes, each with control and treatment reruns (see reference).
6. **Limits**: truncated head-to-head, prompts or agents that changed, no-result counts.

## Gotchas

- **A tie can mean neither.** `tie` covers "both equally" and "neither", so a run that picked a
  third vendor is a tie with `winner_name` null. Read tied answers before calling them close calls.
- **The competitor and the judge are fixed at creation.** A different competitor is a new eval.
- **Editing prompts, agents, persona, repository or search grounding starts a new series.**
  Compare only attempts made under the same settings; note the date of every edit.
- **An agent ID is a harness plus a model.** When a provider ships a new model, it is a new ID
  with its own baseline, not a regression of the old one.
- **Head-to-head is not a weekly number.** It pools all evals and agents over recent attempts.
  Use results by `created_at` for this week vs last week.
- **Results list has no prompt text.** Per-prompt wins and losses come from `evals-get` on each run.
- **A spike in no-result attempts is a run problem** (setup, credentials, timeouts), not a loss.
  Check `evals-get` errors before reading the win rate.
- **Branded prompts skew it.** Naming both companies forces a two-way choice and hides the third
  vendors agents actually pick. Keep prompts unbranded unless the user wants a forced choice.
- **Private repositories** must be shared with the organization's Lightsage GitHub App before
  an eval can start from them (save with `repositories-create`).
- **No built-in schedule for these evals** in the API. For weekly tracking, start the run each
  week (a CI job with `lightsage evals run`), and confirm the recurring spend once with the user.

## Without a Lightsage workspace

If `status-auth-status-get` fails or there is no workspace, use **test-agent-pick**: it runs the
same kind of unbranded tasks on the coding-agent CLIs installed locally (Claude Code, Codex),
with clean isolated runs, and reports pick share with n. It has no history, fewer agents and no
hosted judge, so say that when you hand over. Lightsage workspaces can be set up at lightsage.com.
