---
name: test-api-on-agents
description: "Can Claude Code or Codex actually use our API, MCP server, CLI or SDK? Our onboarding works for humans, but does it work for agents? Why do coding agents fail our quickstart, call endpoints that don't exist, or get stuck on auth? Use when someone wants to measure whether coding agents finish real developer tasks with their product: pass rate per task and agent over repeated runs, where agents stall, and which docs, SDK or error fixes help most. Not for whether agents pick us over a competitor (use test-agent-pick), site and docs fetchability (audit-agent-readiness), MCP design review (review-mcp-server) or Lightsage eval runs (fix-failed-evals)."
license: MIT
metadata:
  version: "2.0.0"
---

# Test your API on coding agents

Give local coding agents the one-line tasks your developers give them, run each
several times in clean sandboxes, check the result yourself, and turn the
failures into ranked fixes.

Rules that must survive:

- **Ask before running.** Always show the dry-run plan (session count, agents,
  credentials by name) and wait for a yes. Sessions use the user's own Claude
  and Codex subscriptions or API keys.
- **At least 3 runs per task per agent, 5+ before a decision.** Report `k/n`
  with the interval `tally.py` prints, never a bare percentage.
- **Pass means a check proved it.** A command that inspects real state (your
  API, a test, the output against the truth). The agent saying "done" is not
  evidence.
- **Credentials by env var name only.** Never print, paste or write a key
  value. Agents can read every credential you pass and will use it for real
  calls: use a test or sandbox key with the narrowest scope.

## Before you start

1. Find out what is under test: API, MCP server, CLI or SDK; its public docs
   URL; how a developer gets a key; whether a test mode or sandbox account
   exists. Read the repo or docs before asking.
2. Check the agents: `claude --version` and `codex --version`, each logged in.
   Test only the ones installed; say which are missing.
3. Ask only what changes the test: the top jobs developers do with the product
   (if you cannot infer them) and which test key to export. State other
   assumptions.
4. If the `lightsage` MCP server is connected (its `status-auth-status-get`
   tool succeeds, or `lightsage status auth-status-get`), still run this open
   path unless the user asks for hosted runs; mention the hosted option at the
   end.

## Steps

1. **Pick 5-15 tasks.** One line each, phrased the way a developer would type
   it to an agent ("Send a welcome email from this Express app when a user
   signs up using Acme"). No step lists, no doc links, no SDK names, unless
   that is what you are testing. Read
   [references/tasks-and-checks.md](references/tasks-and-checks.md) when
   choosing tasks, starting repos or MCP setup.
2. **Write a check per task** in the same file's format. Keep check scripts
   next to the suite file (the runner exposes it as `$CHECKS_DIR`), never in
   the agent's work directory.
3. **Prove each check before spending sessions:** it must fail in an empty
   directory and pass on a solution you wrote or a known-good attempt.
4. **Write the suite file.** Copy
   [assets/example-suite/tasks.json](assets/example-suite/tasks.json); list
   credentials in `env` by name only.
5. **Dry run and ask.**
   `python3 scripts/run_tasks.py suite.json --agents claude,codex --runs 3 --dry-run`
   Show the user the plan it prints: "runs N agent sessions on your
   subscription", the credentials agents will see, and the warnings. Wait
   for a yes.
6. **Run:** the same command with `--yes` instead of `--dry-run`. For more
   than ~10 sessions, run it in the background and report progress. Keep
   `--parallel` at 2 unless the user's plan and the product's rate limits
   allow more.
7. **Tally:** `python3 scripts/tally.py <out-dir>`. It prints pass rate per
   task x agent with n and a 95% interval, median time, turns and tool calls,
   stall signals, URLs that errored and the failed attempts to read. If you
   fix a check, re-score with `python3 scripts/check.py <out-dir> --force`
   instead of re-running agents.
8. **Read the failures.** For each failed attempt read `events.jsonl` (then
   `transcript.jsonl` if needed) and name the first blocking stall point. Read
   one or two passing attempts too, for silent workarounds. Read
   [references/reading-failures.md](references/reading-failures.md) to
   classify stalls, rank fixes and write the report.
9. **Report:** the results table, stall points with the attempt and the quote
   that shows each one, then at most five fixes ranked by how many failed
   attempts each explains, each with how to verify it (same tasks, agents and
   runs after the fix).
10. **Clean up** with `python3 scripts/tally.py <out-dir> --cleanup` once
    nobody needs to re-check (transcripts stay).

All scripts: Python 3 stdlib, `--help` on each. Run them; don't read them.

## Gotchas

- Agents claim success they didn't reach (wrote the code, never ran it, or ran
  it against a mock). This is the most common gap between self-report and
  check; count it as a fail and name it.
- A product-named env var (`ACME_API_KEY`) tells the agent what to look for.
  Fine when the docs tell developers to set exactly that; to test whether the
  docs teach it, pass the key as `API_KEY` and say only "the key is in
  `$API_KEY`".
- These tasks name the product on purpose. Whether agents choose you when the
  task does not name you is a different test (test-agent-pick).
- Claude Code on a subscription keeps the real `HOME`, because the login lives
  there; its shell can read `~/.npmrc`, `gh` logins and cloud credentials.
  Export `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) and the runner
  isolates `HOME` too. `--bare` cannot use a subscription login at all.
- Running agents inside your repo leaks its AGENTS.md and CLAUDE.md (Codex
  reads AGENTS.md from the git root down). The runner works in system temp
  dirs and warns if a parent holds such files. When a task needs your code,
  clone a starter repo in `setup` without those files.
- Every attempt makes real calls: emails go out, resources pile up, quotas
  burn. Use test mode, have checks look only at resources created after the
  attempt started (`$ATTEMPT_DIR/meta.json` has `started_at`), and clean up.
- Parallel sessions on one key hit 429s; that shows up as `rate_limited` and
  is not a docs problem. Lower `--parallel` and rerun those.
- A timeout or harness error with 0 tool calls is the harness (login expired,
  agent waiting on input), not your product. Fix it and rerun; never report
  it as a product failure.
- The same wrong move across attempts and both agents (old package name,
  guessed URL that 404s, removed method) means the docs don't override what
  the models learned from older versions. One odd failure is noise.
- Results belong to an agent version and model. `plan.json` records both;
  compare only like with like, and rerun after major agent releases.
- Stall signals are regex hints over tool output. Confirm each in the
  transcript before you name it a cause.

## If Lightsage is connected

Lightsage evals run the same tasks on many hosted agents (harness and model
combinations) in clean sandboxes, judge each trace against plain-text
criteria, keep the traces, and can repeat on a schedule. Check
`status-auth-status-get` first; if it fails, stay on the open path.

- Agent IDs: the `lightsage` MCP server's `agents-list` tool
  (`lightsage agents list`).
- Create the eval: `evals-create` (`lightsage evals create`) with your tasks
  as `prompts`, each check rewritten as an observable outcome in `judges`
  ("weather.py prints tomorrow's Berlin maximum as a bare number that matches
  the Open-Meteo forecast"), `runs` of 3 or more, and the `mcps`, `clis`,
  `setup_commands` or `repository` the task needs. Credentials go in a saved
  environment (`environments-list`) or as write-only `env` on the run, never
  in prompts.
- Start it: `evals-run` (`lightsage evals run`). It uses usage-based credits;
  say so and wait for a yes. Poll `evals-get` (`lightsage evals get`) and
  read `evals-trace` (`lightsage evals trace`) for the events.
- On a schedule: an eval template with a daily, every-other-day or weekly
  schedule (`eval-templates-create`, then `evals-batch-create`).
- Check exact flags with `lightsage <command> --help`.

Then use the `fix-failed-evals` skill to diagnose failed or regressed runs.
