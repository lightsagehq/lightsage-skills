# Tasks, checks and the suite file

Contents
- Choosing tasks
- Writing checks
- Suite file format
- Starting from a repo, MCP servers and CLIs
- Examples by surface

## Choosing tasks

Aim for 5-15 tasks. Fewer misses the failures that matter; more makes each
re-run expensive (tasks x agents x runs sessions).

Where good tasks come from, in order:

1. The first job a new developer does: the quickstart's outcome, stated as a
   goal ("Send a test SMS to +15555550100 with Acme").
2. The 3-5 integration jobs that drive adoption or revenue, phrased the way a
   developer asks an agent inside an existing app ("Add Acme login to this
   Next.js app").
3. Jobs that support tickets say developers get wrong (pagination, webhooks,
   idempotency, auth refresh, a breaking change in the last major version).
4. One or two multi-step jobs (create, then update, then verify) to see whether
   agents recover from an error halfway.

Phrase each task as one or two sentences:

| Good | Bad |
|---|---|
| "Using Acme, send a welcome email to new-user@example.com from this script." | "Install acme-node@4, import Emails, call emails.send() with..." (steers) |
| "Create a webhook in my Acme account that posts payment events to https://example.com/hook." | "Read https://docs.acme.com/webhooks and create a webhook" (gives away discovery) |
| "Write list_invoices.py that prints my 3 newest Acme invoice IDs, one per line." | "List invoices" (no observable result to check) |

- Name the output when the check needs it (a file name, "print the ID"), the
  way a real developer would. Don't name packages, methods, endpoints or URLs
  unless the test is "can the agent follow this doc link".
- Keep the product's name in the task. These are capability tests, not pick
  tests.
- Vary nothing between runs. Same prompt, same start state; the variance you
  measure should come from the agent.
- Write prompts in the language your developers use; if you test several SDK
  languages, make them separate tasks (`send-email-python`, `send-email-node`).

## Writing checks

A check is a shell command run in the attempt's work directory after the
agent exits. Exit 0 = pass. It gets `WORKDIR`, `FINAL_MESSAGE_FILE`,
`ATTEMPT_DIR`, `CHECKS_DIR` and the credential env vars named in the suite.

Rules:

- **Check the effect at the source of truth.** Query your API for the created
  resource, run the code the agent wrote and compare its output with the truth
  fetched independently, or run the repo's tests. A file existing is not
  success.
- **Never trust the final message alone.** Use `FINAL_MESSAGE_FILE` only to
  read an ID or URL the agent was asked to print, then verify that ID or URL.
- **Fail on nothing.** Run the check in an empty directory before any agent
  run; it must fail. Then make it pass on a solution you wrote.
- **Only count what this attempt made.** Read `started_at` from
  `$ATTEMPT_DIR/meta.json` and ignore older resources, or the second run passes
  on the first run's email.
- **Keep checks out of reach.** Check scripts live in `$CHECKS_DIR`, not the
  work directory; an agent that can read the check writes to it.
- **Print one line of evidence** (what was compared, what was found). It lands
  in `check.json` and makes failures quick to read.
- **Be as strict as a reviewer, not stricter.** Accept any correct approach
  (SDK or raw HTTP, any file layout) unless the task required one.

Pattern for "created after start", in Python:

```python
import json, os, datetime
started = datetime.datetime.fromisoformat(
    json.load(open(os.path.join(os.environ["ATTEMPT_DIR"], "meta.json")))["started_at"])
# ...list resources from your API with os.environ["ACME_API_KEY"],
# keep those with created_at >= started, exit 0 if the expected one is there
```

If a check turns out wrong after a run, fix it and re-score without new agent
sessions: `python3 scripts/check.py <out-dir> --force` (work dirs must still
exist; don't run `--cleanup` before you're sure).

## Suite file format

```json
{
  "suite": "acme-email",
  "env": ["ACME_API_KEY"],
  "setup": ["git clone --depth 1 https://github.com/acme/express-starter ."],
  "mcp_servers": {
    "acme": { "url": "https://mcp.acme.com/mcp", "bearer_env": "ACME_API_KEY" }
  },
  "timeout_sec": 600,
  "tasks": [
    {
      "id": "welcome-email",
      "prompt": "When a user signs up in this Express app, send them a welcome email with Acme.",
      "check": "python3 \"$CHECKS_DIR/check_welcome_email.py\"",
      "timeout_sec": 900
    }
  ]
}
```

- `env`: names of variables exported in the user's shell. The runner passes
  only these plus basics like `PATH`; values are redacted from every saved
  file. Missing names stop the run.
- `setup`: shell commands run in each fresh work directory before the agent
  starts (suite-level, then task-level). A failed setup marks the attempt as a
  harness error, not a fail.
- `mcp_servers`: attached to both agents. HTTP: `url` plus optional
  `bearer_env`. Local: `command`, `args`, and `env` (names). No secret values
  go into config files; both CLIs read them from the environment.
- `timeout_sec`: per attempt; the agent's process group is killed at the limit
  and the attempt counts as a timeout (a fail).
- Task `id`: lowercase letters, digits, `-`, `_`.

## Starting from a repo, MCP servers and CLIs

- **Existing app tasks** start from a public starter repo cloned in `setup`.
  Remove agent context files from it in setup (`rm -f AGENTS.md CLAUDE.md`)
  unless they are part of what you ship to developers.
- **MCP server tests**: decide what you measure. "Can agents use our MCP
  server" attaches it via `mcp_servers` and asks for the outcome without
  naming tools. "Do agents do better with our MCP server" runs the same tasks
  in two suites, with and without it, same agents and runs, and compares
  pass rates.
- **CLI tests**: install the CLI in `setup` only if a developer's agent would
  find it installed; otherwise leave installation to the agent, which is part
  of the test. A CLI that opens a browser for login will hang the agent: pass
  a token by env var the way your CI docs say.
- **Skill or docs file tests** (llms.txt, an AGENTS.md snippet you publish,
  an agent skill): same tasks with and without the file in the start state.

## Examples by surface

| Surface | Task | Check |
|---|---|---|
| REST API | "Using the Acme API, add a contact named Ada Test with email ada.test@example.com to my account." | List contacts by that email via the API; pass if one was created after `started_at`, then delete it. |
| SDK in an app | "Add Acme email sending to this Express app: POST /signup should send a welcome email." | Start the app, POST /signup with a test address, then query Acme for a message to that address after `started_at`. |
| CLI | "Use the Acme CLI to deploy this folder as a static site and print the URL." | Read the URL from `FINAL_MESSAGE_FILE`, fetch it, pass if it returns 200 with the folder's marker text. |
| MCP server | "Find my three most recent Acme invoices and write their IDs to invoices.txt." | Fetch the three newest invoice IDs from the API; pass if `invoices.txt` matches. |
| Public API, no key | "Write weather.py that prints tomorrow's maximum temperature for Berlin from Open-Meteo." | Run `weather.py`; compare with Open-Meteo's own value (see `assets/example-suite/`). |
