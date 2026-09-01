# Running and diagnosing evals

## Build the request body

`eval-runs create` takes no field flags. Pass the whole body as `--request`,
or pipe it on stdin. A `type` field selects one of two shapes:

**Prompt runs** (`type: prompts`) run Visibility prompts across platforms.
Only `type` is required:

```bash
lightsage eval-runs create --no-interactive --request '{
  "type": "prompts"
}'
```

Omit `prompt_ids` to run all active prompts, and omit `targets` to use the
configured scheduled targets. Set `force` to re-run a prompt that already ran
today.

**API Performance runs** (`type: api_performance`) require `source_type` as
well:

```bash
lightsage eval-runs create --no-interactive --request '{
  "type": "api_performance",
  "source_type": "rest_api",
  "source_id": "<id from api-performance sources list>"
}'
```

`source_type` accepts `rest_api`, `sdk`, `cli`, and `custom_evals`. The first
three run a configured source's eval definitions and need `source_id`.
`custom_evals` runs custom eval definitions instead, selected with
`custom_eval_ids`.

Narrow a run with `operation_ids`, `operation_paths`, `eval_ids`,
`eval_types`, or `targets`. Every selection field you omit falls back to saved
config, so a body with nothing runnable fails with 400 rather than running
everything.

## Poll on status and nothing else

The call returns as soon as the run is queued, and the response `id` is the
only handle you will ever get: there is no `eval-runs list`, so a lost id
means an unpollable run. Persist it before doing anything else.

That id is also a different ID space from the result rows in
`api-performance runs`. Passing a result-row id to `eval-runs retrieve`
returns 404.

Poll with the returned `id`:

```bash
lightsage eval-runs retrieve --eval-run-id "$ID" --no-interactive -o json --jq '.status'
```

`--jq` emits JSON-encoded values, so that returns `"completed"` with quotes. A
shell comparison against `completed` never matches and the loop spins forever.
Strip them with `tr -d '"'`, or parse the whole response with your own `jq -r`.

| Status | Meaning |
| --- | --- |
| `pending`, `running`, `summarizing` | Still in flight |
| `completed`, `failed`, `cancelled`, `interrupted` | Terminal |

Stop only on a terminal status. While `status` is `summarizing`, `progress`
already reports 100% and `completed_at` is already set, so an agent watching
either field concludes the run finished before it did. `estimated_cost` is
null during the same window.

No command cancels a run. Once created, a run reaches a terminal status on its
own.

## Read the results

Runs and results live in different places:

- `api-performance runs list` returns completed result rows — one operation,
  one model, one verdict — newest first. Custom eval rows are excluded. Always
  pass `--limit`; without it the command can hang for minutes. The response
  carries no pagination cursor, so reach older runs by narrowing `--since`,
  which accepts `7d`, `72h`, or an ISO 8601 date.
- `api-performance runs retrieve` returns one row in full, with prompts,
  output, logs, and tool calls. The list carries summary fields only.
- `api-performance custom-evals history list` returns custom eval results,
  and takes `--limit` and `--offset`.

## Diagnose failures

`api-performance diagnose` reports failure patterns across a window rather
than a single run:

```bash
lightsage api-performance diagnose --no-interactive --since 20d --format-param markdown
```

`--since` accepts a duration such as `20d` or `72h`, or an ISO timestamp, and
defaults to 20 days. `--format-param` chooses `json` (default), `markdown`, or
`md`. Example failed runs are included by default; cap them with
`--max-examples` or drop them with `--include-examples=false`.

Note that `--format-param` controls the report inside the response, not the
CLI's own output format. `--output-format` still applies.

## Know what a run costs

Cost follows the platform, and you can read it rather than assume it:

```bash
lightsage prompts config retrieve --no-interactive -o json \
  --jq '.platforms[] | {name, credits_per_prompt}'
```

Coding agents cost 5 credits per prompt; answer engines cost 1. Read the live
value before quoting a figure, because the catalog changes.

Note the scope: `credits_per_prompt` is a **Visibility prompt** platform cost.
It does not describe what an API Performance run costs, which follows that
run's targets. Do not quote it as the price of an eval run.

`estimated_cost` on a run is US dollars, not credits.

If a run fails because the organization is out of credits, stop and report it.
Retrying cannot succeed.
