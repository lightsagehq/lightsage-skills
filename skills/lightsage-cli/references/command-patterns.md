# Lightsage CLI command patterns

These examples illustrate reusable mechanics verified against Lightsage CLI
0.6.7. Re-check the installed binary before copying them into an execution.

## Discover the surface

```bash
lightsage version
lightsage --usage
lightsage evals configurations create --help
```

Use `--usage` before help when the command path is uncertain. The help for a
known command is the source for required flags, enum values, and defaults.

## Check configuration and authentication

```bash
lightsage auth whoami
lightsage status auth-status-get --output-format json
```

The first command inspects configured credential sources and masks values. The
second validates the credential with Lightsage.

## List, select, then retrieve

```bash
lightsage eval-results list --since 7d --limit 20 --output-format json
lightsage eval-results retrieve \
  --result-id "$LIGHTSAGE_RESULT_ID" \
  --output-format json
```

Set `LIGHTSAGE_RESULT_ID` from the list response. Do not substitute an eval-run
ID. If the list is empty, stop and report that there is no completed result to
retrieve.

Use `--jq` after seeing the full response shape:

```bash
lightsage eval-results list --limit 20 --output-format json
lightsage eval-results list --limit 20 --jq '.data[] | {id, passed, score}'
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

## Prefer flags until a body is clearer

Use individual flags for short operations because required fields remain
visible. Use `--body` or stdin for deeply structured values such as judge
objects or when quoting would otherwise become error-prone. Do not supply the
same field through both a flag and the body unless current help defines the
precedence.
