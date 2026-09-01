# Resource model

## What you can do to each resource

| Resource | Command group | Create | Read | Update | Delete |
| --- | --- | --- | --- | --- | --- |
| Eval definitions | `api-performance evals` | — | ✓ | ✓ | — |
| Custom evals | `api-performance custom-evals` | ✓ | ✓ | ✓ | ✓ |
| Starter projects | `api-performance starter-projects` | ✓ | ✓ | ✓ | ✓ |
| Actions | `api-performance actions` | — | ✓ | ✓ | — |
| Config | `api-performance config` | — | ✓ | ✓ | — |
| Targets | `api-performance targets` | — | list only | — | — |
| Sources | `api-performance sources` | — | list only | — | — |
| Skills | `api-performance skills` | — | list only | — | — |
| Run history | `api-performance runs` | — | ✓ | — | — |
| Eval runs | `eval-runs` | ✓ | ✓ | — | — |
| Prompts and topics | `prompts` | ✓ | ✓ | ✓ | ✓ |
| Tasks | `tasks` | — | ✓ | ✓ | — |
| Opportunities | `opportunities` | — | list only | — | — |
| Visibility | `visibility` | — | ✓ | — | — |
| Site audit | `site-audit` | — | ✓ | — | — |
| Content | `content` | ✓ | ✓ | — | — |

## Read the catalogs, change the config

Targets, sources, and skills are catalogs. You cannot create or edit them:

- **Sources** are configured for the workspace and cannot be created or edited
  from the CLI; `--source-id` only scopes other commands. `sources list` hides
  the sources Lightsage manages itself, such as `use_cases`, unless you pass
  `--include-system`.
- **Targets** list the models and coding agents evals can run against. To
  change what runs, copy a `target` object into `config update`.
- **Skills** list what can be supplied as skill context. To change what an
  eval uses, pass `skill_ids` to `evals update` with `skills_mode` set to
  `selected`. `skills list` filters silently: omitting `--enabled` returns
  only enabled skills, and omitting `--stale` returns only non-stale ones, so
  the default listing is a subset.

## Tell the eval resources apart

Four resources share the word "eval":

| Resource | What it is | Created by |
| --- | --- | --- |
| Eval definitions | One check per discovered API operation | Lightsage, from a source |
| Custom evals | A free-form task prompt | You |
| Eval runs | A queued execution | `eval-runs create` |
| Run history | Completed result rows | Runs finishing |

Two relationships explain the overlap:

- Every custom eval owns an eval definition. That definition also appears in
  `api-performance evals list`, carrying `source_id` null and an
  `operation_id` equal to the custom eval's ID.
- `api-performance runs list` returns result rows, not jobs, and excludes
  custom eval rows. List those with
  `api-performance custom-evals history list`.

## Follow the ID chain

| ID | Comes from |
| --- | --- |
| `topic_id` | `prompts config retrieve` — there is no topics list command |
| `source_id` | `api-performance sources list` |
| `skill_ids` | `api-performance skills list` |
| `custom_eval_id` | `api-performance custom-evals list` |
| `eval_id` / `operation_id` | `api-performance evals list` |
| `eval_run_id` | the `id` returned by `eval-runs create` — there is no `eval-runs list`, so keep it |
| `env_profile_ids` | `env_profiles[]` in `api-performance config retrieve` |
| `target` | copy the whole object from `api-performance targets list` |
| `content_id` | the `id` returned by `content generate-draft` — no endpoint lists content, so keep it |
| `task_id` | `tasks list` |
| `action_id` | `api-performance actions list` |

## Know what is not possible

- No command cancels a run, despite the `jobs:cancel` scope.
- The site audit is read-only.
- Secret values are write-only. `api-performance config retrieve` returns
  environment variable names in `env_var_keys` and in each entry of
  `env_profiles`, never values.
- Paging is uneven. `api-performance custom-evals history list` takes
  `--limit` and `--offset`; `api-performance runs list` and
  `opportunities list` take `--limit` and `--since`;
  `api-performance actions list` takes `--limit` only. `prompts list`,
  `tasks list`, and `api-performance evals list` are unpaginated and return
  everything.
- `api-performance runs list` returns no pagination cursor, so reach older
  runs by narrowing `--since`, not by paging.
