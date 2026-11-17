# Lightsage CLI command patterns

These examples illustrate reusable mechanics verified against the Lightsage CLI
0.11.24 source (2026-11-17). Re-check the installed binary before copying them
into an execution.

## Contents

- Discover the surface
- Check configuration and authentication
- Get JSON in agent environments
- List, select, then retrieve
- Repeat list-valued flags
- Preview a write
- Start and poll a run (after the credit yes)
- Read plugin eval results
- Run in CI
- Prefer flags until a body is clearer

## Discover the surface

```bash
lightsage version
lightsage --usage
lightsage evals configurations create --help
```

Use `--usage` before help when the command path is uncertain. The help for a
known command is the source for required flags, enum values, and defaults.
`--usage` also works on one subtree: `lightsage evals run --usage`.

For commands that take a request body, print its exact JSON Schema:

```bash
lightsage prompts run --schema
lightsage evals run --schema
```

None of these need credentials or call the API.

## Check configuration and authentication

```bash
lightsage auth whoami
lightsage status auth-status-get --output-format json
```

The first command inspects configured credential sources and masks values. The
second validates the credential with Lightsage.

## Get JSON in agent environments

When the CLI detects an agent environment (Claude Code, Cursor and others) it
switches to agent mode: structured errors and TOON output by default. Ask for
JSON explicitly whenever output is parsed:

```bash
lightsage prompts list --output-format json --no-interactive
```

`--agent-mode=false` turns agent mode off if a person is reading the output.

## List, select, then retrieve

```bash
lightsage eval-runs list --limit 20 --output-format json
lightsage evals get "$LIGHTSAGE_EVAL_RUN_ID" --output-format json
```

Set `LIGHTSAGE_EVAL_RUN_ID` from the list response. Once a run finishes,
`evals get` also returns its per-attempt `results` and `analysis`; there is no
separate result command. If the list is empty, stop and report that there is no
eval run to retrieve.

Use `--jq` after seeing the full response shape:

```bash
lightsage eval-runs list --limit 20 --output-format json
lightsage eval-runs list --limit 20 --jq '.data[] | {id, status, eval_name}'
```

Treat filtered values as JSON. Do not assume a scalar is emitted as unquoted
raw text in a shell comparison.

## Repeat list-valued flags

For flags described as a list, pass one value per occurrence:

```bash
lightsage evals configurations create \
  --eval-id "$LIGHTSAGE_EVAL_ID" \
  --name "Candidate with CLI skill" \
  --cli-ids "$LIGHTSAGE_CLI_ID" \
  --skill-ids "$LIGHTSAGE_SKILL_ID" \
  --dry-run
```

For two skills, repeat the flag:

```bash
--skill-ids "$LIGHTSAGE_PRIMARY_SKILL_ID" \
--skill-ids "$LIGHTSAGE_SUPPORTING_SKILL_ID"
```

Inspect the dry-run body and confirm that each value became its own array
element. Do not pass a JSON array string to a repeated string flag unless the
current command explicitly requires JSON.

## Preview a write

```bash
lightsage repositories create \
  --name "Acme API" \
  --repo-url "https://github.com/acme/example-api.git" \
  --ref main \
  --dry-run
```

Dry-run output is diagnostic output and may be written to stderr. It must say
that the network call was skipped. Summarize the method, URL, and request body
for the user; do not claim that the repository was created.

If the user's request clearly authorizes this exact creation, rerun the command
without `--dry-run` and retrieve the returned resource. Ask only if the preview
reveals a different target, effect, or scope.

## Start and poll a run (after the credit yes)

Runs use usage-based credits. Preview first, tell the user the fan-out, and run
only after a yes.

```bash
lightsage prompts run \
  --body '{"prompt_ids": ["'"$LIGHTSAGE_PROMPT_ID"'"]}' \
  --dry-run
lightsage prompts run --body '{"prompt_ids": ["'"$LIGHTSAGE_PROMPT_ID"'"]}' --output-format json
lightsage prompts run-status "$LIGHTSAGE_PROMPT_RUN_ID" --output-format json
```

Omitting `prompt_ids` runs every active prompt on the configured targets. Repeat
`--agent <agent-id>` (IDs from `lightsage agents list`) to run on specific coding
agents instead of the configured targets.

```bash
lightsage evals run --eval-id "$LIGHTSAGE_EVAL_ID" --agent "$LIGHTSAGE_AGENT_ID" --runs 3 --dry-run
lightsage evals get "$LIGHTSAGE_EVAL_RUN_ID" --output-format json
lightsage evals monitor --run-id "$LIGHTSAGE_EVAL_RUN_ID"
```

Poll until the status is terminal, not until progress reads 100 percent.

## Read plugin eval results

```bash
lightsage plugin-evals results-list --date 2026-11-16 --output-format json
curl -o plugin-results.zip "$DOWNLOAD_URL"
```

The `download_url` in each result works without an API key for 15 minutes. A
`404` means no results for that date; a `403` on download means the link expired,
so list again for a fresh one.

## Run in CI

```bash
# LIGHTSAGE_API_KEY comes from the CI secret store, never from the repo
lightsage status auth-status-get --no-interactive --output-format json
lightsage visibility current-retrieve --no-interactive --output-format json > visibility.json
```

Fail the job on a non-zero exit code. Never echo the key or run with `--debug`
in shared logs without checking that headers are masked.

## Prefer flags until a body is clearer

Use individual flags for short operations because required fields remain
visible. Use `--body` or stdin for deeply structured values such as judge
objects or when quoting would otherwise become error-prone. Do not supply the
same field through both a flag and the body unless current help defines the
precedence.
