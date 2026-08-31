# Command conventions

## Pass values in the right shape

Scalar flags take plain values. List- and object-typed flags take JSON, even
though `--help` types them as `string`:

```bash
lightsage api-performance evals update --eval-id "$ID" --docs-mode include
lightsage api-performance config update --source-id "$SID" \
  --custom-eval-ids '["11111111-1111-1111-1111-111111111111"]'
```

Each mistake fails differently:

| You did | Result |
| --- | --- |
| Plain value to a list flag | Rejected: `error unmarshalling json response body` |
| JSON-quoted scalar to an enum | Rejected as an invalid option |
| JSON-quoted scalar to a free string | Accepted and stored **with its quotes** |

The third is the dangerous one, because nothing reports it. When a flag's
description mentions a plural or an array field, treat it as JSON.

## Send a whole body instead of flags

Write commands that carry a request body accept `--body` with the entire JSON
payload, as an alternative to individual flags, and also read it from stdin:

```bash
echo '{"status":"done"}' | lightsage tasks update --task-id "$ID"
```

Two exceptions: `eval-runs create` has no field flags at all and takes only
`--request`, so you always build the body yourself. ID-only writes such as
`api-performance actions verify` and every `delete` take neither flag —
passing `--body` to one fails with `unknown flag: --body`.

## Read the help layout

Help splits flags into **Required Flags** and **Optional Flags** rather than a
single `Flags:` block. When you grep help output, match both.

Many commands carry a short alias, shown under `Aliases:` — for example `apal`
for `api-performance actions list`. Others, including everything under `tasks`
and `eval-runs`, have none.

## Choose an output format

`--output-format` (`-o`) accepts `pretty` (default), `json`, `yaml`, `table`,
and `toon`. Use `json` for parsing and `toon` for a compact form that costs
fewer tokens.

Filter with `--jq` rather than piping, so you avoid a second process:

```bash
lightsage prompts config retrieve --no-interactive -o json \
  --jq '.platforms[] | {name, credits_per_prompt}'
```

Always pass `--limit` to `api-performance runs list`. Omitting it hangs
indefinitely, while `--limit 20` returns in about two seconds — even though
both send the identical request `?limit=20`. The maximum accepted is 200.

`--jq` emits JSON-encoded values, so `--jq '.status'` returns `"completed"`
with quotes. Strip them before comparing in a shell.

## Inspect a request before sending it

`--dry-run` prints the URL, headers, and body, then stops. **It writes to
stderr, not stdout**, so a command that captures only stdout sees nothing and
may look like it did nothing:

```
[DRY-RUN] Would send: PUT https://api.lightsage.com/v1/api-performance/config
[DRY-RUN] Headers:
    Content-Type: application/json
    X-Lightsage-Api-Key: [REDACTED]
[DRY-RUN] Body:
  {
    "custom_eval_ids": ["1111…"],
    "source_id": "b6e7…"
  }
[DRY-RUN] Network call skipped.
```

Use it to confirm a value landed as an array rather than a string. Use
`--debug` to log request and response diagnostics to stderr on a real call.

## Run as an agent

`--agent-mode` turns on structured errors and defaults output to TOON. It
switches on automatically in known agent environments, including Claude Code
and Cursor; pass `--agent-mode=false` to opt out.

In agent mode, a failed command still prints the human-readable block, then
adds a machine-readable line carrying only the `detail` — with no status code.
Parse the detail, not the status.

`detail` has two shapes, so check the type before reading it:

```json
{"detail": "Invalid API key"}
{"detail": [{"loc": ["body","api_performance","source_type"],
             "msg": "Input should be 'rest_api', 'sdk', 'cli' or 'custom_evals'",
             "type": "literal_error"}]}
```

A string is an API error. An array is request validation: each entry names the
offending field in `loc` and what was expected in `msg`. Read `loc` to find
which field to fix. Some errors add a `code` field carrying a database error
code — ignore it.

## Tell two near-identical errors apart

Two unrelated failures differ by one letter. Match the prefix, never the
substring:

| Message | Means |
| --- | --- |
| `invalid value for --<flag>: error unmarshalling json response body` | **Your flag** wanted JSON. Two `l`s. |
| `error unmarshaling json response body` | **The response** could not be parsed. One `l`. |

Only the first carries the `invalid value for --<flag>:` prefix. Keying on
`unmarshal` alone makes an agent "fix" a flag that was already correct.

## Discover the command tree

`lightsage --usage` emits the whole command tree as KDL — every command,
alias, and flag in one machine-readable document. Use it to enumerate, and
trust it over any documentation.

Use `--help` for what it is good at: the flags, defaults, and enum values of a
command you already know exists. It is reliable for that and it is how you
should learn any unfamiliar command's inputs.

What `--help` cannot do is prove a command exists. A genuinely unknown command
errors and exits 1, but adding `--help` makes it print help and exit 0 instead
— root help for an unknown top-level command, the parent group's help for an
unknown subcommand. Invoking a group with no subcommand does the same. To test
existence, run the command.
