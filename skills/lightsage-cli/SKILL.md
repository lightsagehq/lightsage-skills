---
name: lightsage-cli
description: Drive the Lightsage CLI — authentication, choosing the right command and resource, flag and output conventions, running and polling evals, and acting on findings. Use for any task that invokes the `lightsage` binary or mentions the Lightsage CLI, API Performance, custom evals, starter projects, env profiles, eval runs, visibility score, share of voice, tracked prompts and topics, site audit, content drafts, or Lightsage tasks, opportunities, and actions. Covers install, API keys and CI setup, the eval resource model, where IDs come from, run polling and diagnosis, and credit costs.
metadata:
  version: 0.1.0
---

# Lightsage CLI

The `lightsage` CLI manages Lightsage prompts, custom evals, and API
Performance from the command line. It wraps the same public API as the MCP
server and `api.lightsage.com/v1`, and it is the right interface for CI and
for any workflow that polls, filters, or scripts output.

When documentation and the binary disagree, trust the binary: run
`lightsage --usage` for a machine-readable command tree.

## Get connected

Install the CLI and confirm it runs:

```bash
brew install lightsagehq/tools/lightsage
lightsage version
```

If you are an agent or running in CI, authenticate with the environment
variable and pass `--no-interactive` on every command, which suppresses
prompting and the TUI:

```bash
export CLI_LIGHTSAGE_API_KEY_AUTH="<key>"
lightsage status auth-status-get --no-interactive
```

A working key returns `authenticated`, `org_id`, `api_key_id`, and `scopes`.
For local interactive use, run `lightsage auth login` to store the key in the
OS keychain. For all four methods and their precedence, see
[references/auth.md](references/auth.md).

## Resolve the resource before you choose a command

Three separate resources are called "evals". Choosing the wrong one returns a
plausible result rather than an error, so settle the noun first:

| You mean | Resource | Command |
| --- | --- | --- |
| The per-operation checks Lightsage generates for a source | Eval definitions | `api-performance evals` |
| A free-form task prompt you wrote | Custom evals | `api-performance custom-evals` |
| A queued execution of those checks | Eval runs | `eval-runs` |
| The completed result rows | Run history | `api-performance runs` |

The last two are the easiest to confuse. `eval-runs` **starts** work;
`api-performance runs` **reads finished** work. They live in different command
groups. For every resource and what you can do to it, see
[references/resource-model.md](references/resource-model.md).

## Find the ID you need

Most IDs come from the matching `list` command. Three do not, and two of those
are unrecoverable once lost:

| ID | Comes from |
| --- | --- |
| `topic_id` | `prompts config retrieve` — there is no topics list command |
| `eval_run_id` | `eval-runs create` — **keep it**, there is no `eval-runs list` |
| `content_id` | `content generate-draft` — **keep it**, nothing lists content |

For the rest, see
[references/resource-model.md](references/resource-model.md).

## Discover what exists

Three questions, three tools. Using the wrong one is how agents invent
commands:

| To learn | Use | Not |
| --- | --- | --- |
| What commands exist | `lightsage --usage` — the whole tree as KDL | Documentation, which has described commands the binary lacks |
| What flags a command takes | `lightsage <cmd> --help` — flags, defaults, and enum values | Guessing from the API |
| Whether a command is real | Run it. A wrong command errors and exits 1 | `--help`, which prints help and exits 0 either way |

The third row is the trap: adding `--help` to a command that does not exist
prints the parent's help and exits 0, so it looks like it worked.

## Run commands correctly

Scalar flags take plain values. Only list- and object-typed flags take JSON:

```bash
lightsage api-performance evals update --eval-id "$ID" --docs-mode include
lightsage api-performance config update --custom-eval-ids '["<id>","<id>"]'
```

A plain value passed to a list flag is rejected with
`invalid value for --<flag>: error unmarshalling json response body`. Match
that whole prefix, not the word `unmarshal` — a near-identical message without
it means the *response* failed to parse, which is a different problem.

The reverse mistake is quieter: a JSON-quoted scalar is rejected on enums, but
on a free string it is stored with its quotes and nothing reports it.

When you are unsure, add `--dry-run`. It prints the URL, headers, and body
without sending the request, so you can confirm a value landed as an array
rather than a string. It writes to stderr, so capture `2>&1` to see it.

One command breaks this pattern: `eval-runs create` takes no field flags at
all, only the whole body as `--request`. See
[references/conventions.md](references/conventions.md) for output formats,
`--jq`, and diagnostics.

## Run and poll evals

`eval-runs create` queues a durable run and returns immediately. Poll
`eval-runs retrieve` with the returned `id` until `status` is terminal:

- In flight: `pending`, `running`, `summarizing`
- Terminal: `completed`, `failed`, `cancelled`, `interrupted`

Poll on `status` and nothing else. While `status` is `summarizing`, `progress`
reports 100% and `completed_at` is already set, so an agent watching either
field concludes the run finished before it did.

Read results with `api-performance runs list` and `api-performance runs
retrieve`, then `api-performance diagnose` for failure patterns across a run.
For the full chain, see [references/run-evals.md](references/run-evals.md).

## Act on findings

Findings arrive in two shapes, and they take different loops:

| Source | Carries | Loop |
| --- | --- | --- |
| `tasks`, `opportunities` | `execution_prompt` | Run the prompt, open one pull request, then `tasks update` the status |
| `api-performance actions` | `recommendation`, `primary_url`, or a prompt via `actions retrieve --include-prompt` | Fix the URL, run `api-performance actions verify`, confirm the status reaches `verified` |

Open one pull request per item, and treat an item as done only when that pull
request merges. See [references/findings.md](references/findings.md).

## Pitfalls

- On `api-performance actions list`, `--limit` caps `data` but not `counts`,
  and it makes `summary.affected_runs` sum only the rows returned. Read
  totals from `counts`, never by counting `data`.
- Always pass `--limit` to `api-performance runs list`. Without it the command
  can hang for minutes.
- No run cancellation exists, despite the `jobs:cancel` scope.

## References

| Open | When you need |
| --- | --- |
| [references/auth.md](references/auth.md) | Auth methods, precedence, CI setup, key handling |
| [references/conventions.md](references/conventions.md) | Output formats, flag typing, `--jq`, diagnostics |
| [references/resource-model.md](references/resource-model.md) | Every resource, what you can do to it, lifecycles |
| [references/run-evals.md](references/run-evals.md) | Starting, polling, reading, and diagnosing runs |
| [references/findings.md](references/findings.md) | Tasks, opportunities, actions, and the pull-request loop |
