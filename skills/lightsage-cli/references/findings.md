# Acting on findings

Lightsage surfaces work in three places. Tasks and opportunities hand you a
prompt to run; actions hand you a fix to verify, and can generate a prompt on
request.

| Source | Carries | Command group |
| --- | --- | --- |
| Daily tasks | `execution_prompt` | `tasks` |
| Opportunities | `execution_prompt` | `opportunities` |
| API Performance actions | `recommendation`, `primary_url`, and a prompt on request | `api-performance actions` |

## Work a task

`tasks list` returns the daily action queue, ranked. Each task carries
`title`, `why`, `next_action`, `execution_prompt`, `score`, `effort`,
`priority`, and `status`.

Run the `execution_prompt` as given, open one pull request, then move the
task:

```bash
lightsage tasks update --task-id "$ID" --status in_progress --no-interactive
```

`--status` accepts `new`, `in_progress`, `added_to_sheet`, `done`,
`dismissed`, and `snoozed`. The same command reprioritizes with `--priority`
(`urgent`, `high`, `medium`, `low`), delegates with `--assignee-user-id`, and
reclassifies with `--action-type` (`agent_discovery`, `agent_usability`). Send
at least one field; only the fields you send change.

Two of those statuses hide the task. `added_to_sheet` and `snoozed` have no
matching slice in the status filter on `tasks list`, so a task moved there is
only reachable with `status=all`.

## Work an opportunity

`opportunities list` returns ranked content and visibility opportunities
derived from prompt results. Each carries `execution_prompt`, `impact_score`,
`topic_name`, `your_visibility`, and `competitor_visibility`.

Narrow the list with `--category` (`quick_wins`, `growth`, `refresh`,
`citations`), `--opportunity-type`, `--limit`, or `--since`.

Opportunities are list-only. There is no update command — the loop ends with
the pull request, not with a status change.

## Work an action

Actions are concrete defects found on a tracked surface, ordered by priority
with `critical` first. Each carries `recommendation`, `primary_url`,
`affected_urls`, `evidence`, and `status`.

The loop has a verification step the other two lack:

1. Read `recommendation` and fix the URL in `primary_url`. To get a
   ready-to-run instruction instead, retrieve the action with a generated
   remediation prompt:

   ```bash
   lightsage api-performance actions retrieve --action-id "$ID" \
     --include-prompt --no-interactive
   ```

   The `data` object is identical either way; `--include-prompt` only
   populates `prompt`.
2. Run `lightsage api-performance actions verify --action-id "$ID"` to make
   Lightsage re-check the fix.
3. Confirm the status reaches `verified`.

Statuses are `open`, `in_progress`, `ignored`, `fixed`, and `verified`. Set
one directly with `actions update --status`, and give a reason with
`--ignored-reason` when you ignore. `actions refresh` re-scans a source for
new actions.

## Read totals from counts

`actions list` returns `data`, `counts`, and `summary`. The filters do not
narrow all three the same way:

- `--status` and `--priority` narrow `data` only. `counts` and `summary` still
  cover every status and priority.
- `--action-type` and `--source-id` narrow all three.
- `--limit` caps `data`, leaves `counts` alone, and makes
  `summary.affected_runs` and `summary.affected_failed_runs` sum only the rows
  returned.

Read totals from `counts`. Counting `data` gives a number that looks right and
is not.

## Open one pull request per item

Each finding is one pull request. Do not batch several findings into one, and
do not split one finding across several.

An item is done only when its pull request merges. Opening a pull request,
pushing a branch, and marking a task `done` before the merge all report
progress that has not happened.
