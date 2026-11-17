# Setting up an Agent Preference eval

Read before creating, editing or deleting an eval.

## Fields (`agent-preference-evals-create`)

| Field | Required | Notes |
|---|---|---|
| `competitor_id` | yes | From `agent-preference-competitors-list`. Fixed after creation. |
| `prompts` | yes | 1 to 20 buying questions or build tasks. |
| `agent` | no | Agent IDs from `agents-list` (harness plus model), up to 10. An empty list saves the eval with no default agents. |
| `runs` | no | Attempts per prompt per agent. Defaults to 1; set 3 or more. |
| `repository` | no | Starting repo: a built-in alias or saved repository ID from `repositories-list`. Omit for an empty workspace. |
| `search_grounding` | no | `default`, `enabled` or `disabled`. Leave `default` unless the user is testing search on vs off. |
| `persona` | no | One perspective applied to every attempt ("a solo developer on a free tier"). It changes picks; keep it fixed. |
| `name` | no | Defaults to "<your company> vs <competitor>". |
| `tags` | no | For example `weekly`, `email`, `post-docs-change`. |

The limits above are the API's at the time of writing; a validation error names the current ones.
The judge that decides each attempt is fixed and cannot be edited.

## Prompts

- Unbranded. "Which email API should I use for a Next.js app? Pick one." not "Should I use
  YourBrand or Competitor A?" Naming both forces a two-way choice and hides third vendors.
- Mix questions developers ask before choosing ("which X for Y") with build tasks ("add password
  reset emails to this app"). Build tasks need a `repository` that matches the stack.
- Spread across the stacks buyers use; one job per prompt; no feature only one vendor has.
- If the user has a local `tasks.json` from test-agent-pick, reuse its prompts (up to 20 per eval).
- Keep the prompt list stable. Reworded prompts start a new series.

## Agents and runs

- Start from `agents-list`. Pick the agents the user's buyers use; include at least one Claude
  Code and one Codex ID when available. Name them in the confirmation by their `name`, not only ID.
- 3 runs per prompt per agent is the floor; 5 when the user will act on a change. Attempts per
  run of the eval = prompts x agents x runs, for example 12 x 4 x 3 = 144.

## Confirmation (show this, then wait)

```text
Eval: YourBrand vs Competitor A
Prompts: 12 (5 questions, 7 build tasks on nextjs-starter)
Agents: Claude Code (model), Codex (model), Cursor (model), ...
Runs: 3 per prompt per agent
Each run of this eval makes 144 attempts and uses usage-based credits.
Create it? Start the first run now?
```

Ask the two questions separately if the user hesitates; creating costs nothing, running does.

## Editing and deleting

- `agent-preference-evals-update`: omitted fields stay as they are; an empty `agent` or `tags`
  list clears it; `persona: null` clears the persona. The competitor and judge cannot change.
- Any change to prompts, agents, persona, repository, runs or grounding makes later attempts
  incomparable with earlier ones. Prefer a new eval (or a dated tag) for a new series, and tell
  the user which comparison the edit breaks.
- `agent-preference-evals-delete` is permanent. Retrieve the eval first, show its name and
  competitor, and get an explicit yes.

## Weekly cadence

The API has no schedule for these evals. To track weekly, start a run each week with the CLI
(`lightsage evals run` with the eval ID; check flags with `lightsage evals run --help`), from CI
or a scheduled job, and agree the recurring spend with the user once. Run on the same weekday so
periods line up.
