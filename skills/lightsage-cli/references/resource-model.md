# Lightsage resource and command model

Use this reference to translate between a Lightsage resource and the CLI
commands that discover, read, or change it. Command paths were verified against
Lightsage CLI 0.6.7, built 2026-09-06. Re-check `lightsage --usage` and the
specific command's help before execution.

The tables map command paths, not every flag. Obtain required flags and current
enums from the installed binary.

## Core relationships

```text
Topic
└── Prompt
    └── Prompt run

Opportunity    Task    Site audit    Content

Eval
└── Configuration
    ├── Repository
    ├── Environment
    ├── CLI
    ├── Skill
    ├── MCP server
    └── Include docs
        + Agent
          ↓
       Eval run
          ↓
       Eval result
```

These are separate resource lanes. Do not infer that an opportunity owns a task
or that an eval-run ID can retrieve an eval result unless the returned data
explicitly establishes that relationship.

## Workspace and authentication

| Purpose | CLI command |
| --- | --- |
| Inspect configured credential sources | `lightsage auth whoami` |
| Configure credentials interactively | `lightsage auth login` |
| Remove configured credentials | `lightsage auth logout` |
| Check public API availability | `lightsage status get` |
| Validate the current credential | `lightsage status auth-status-get` |

The public status check does not validate the API key. Credential values shown
by `auth whoami` are masked.

## Prompts and visibility work

| Resource | Discover or read | Create or change | ID relationship |
| --- | --- | --- | --- |
| Topic | `lightsage prompts topics list` | `lightsage prompts topics create`, `update`, `delete` | Topic IDs are accepted by prompt list, create, and update operations. |
| Prompt | `lightsage prompts list`, `retrieve` | `lightsage prompts create`, `update`, `delete` | Prompt IDs select a prompt and may filter prompt runs. |
| Prompt run | `lightsage prompts runs list`, `retrieve` | None | A prompt-run ID retrieves one stored answer. |
| Opportunity | `lightsage opportunities list`, `retrieve` | None | An opportunity ID retrieves one computed finding and its execution context. |
| Task | `lightsage tasks list`, `retrieve` | `lightsage tasks update` | A task ID retrieves or updates one persisted action item. |
| Content | `lightsage content retrieve` | `lightsage content drafts create`, `lightsage content finalize` | Draft creation returns a content ID used by retrieve and finalize. |
| Site audit | `lightsage site-audits list`, `retrieve` | None | A site ID retrieves one existing audited-page result. |

Listing and retrieving site audits reads existing data; it does not start a
crawl. Creating drafts and finalizing content consume credits.

## Eval definitions and runtime resources

An eval defines the task and judge. Its type determines the subject:

| Eval type | Subject |
| --- | --- |
| `workflow` | No subject ID |
| `mcp` | One MCP-server ID |
| `cli` | One CLI ID |
| `skill` | One reusable-skill ID |

| Resource | Discover or read | Create or change | Used by |
| --- | --- | --- | --- |
| Eval | `lightsage evals list`, `retrieve` | `lightsage evals create`, `update`, `delete` | Eval ID scopes configurations and starts runs. |
| Configuration | `lightsage evals configurations list`, `retrieve` | `lightsage evals configurations create`, `update`, `delete` | Configuration ID selects the saved runtime for a run. Every configuration command also needs its eval ID. |
| Agent | `lightsage agents list` | None | Agent ID chooses one runnable harness-and-model combination for a run. |
| Repository | `lightsage repositories list`, `retrieve` | `lightsage repositories create`, `update`, `delete` | Repository ID gives a configuration its Git workspace. Creation uses `--repo-url`. |
| Environment | `lightsage environments list` | None | Environment ID gives a configuration its reusable runtime environment. |
| MCP server | `lightsage mcp-servers list` | None | MCP-server IDs may identify an MCP eval subject or support a configuration. |
| CLI | `lightsage clis list` | None | CLI IDs may identify a CLI eval subject or support a configuration. |
| Skill | `lightsage skills list` | None | Skill IDs may identify a skill eval subject or support a configuration. |

`agents`, `environments`, `mcp-servers`, `clis`, and `skills` are list-only in
this CLI version. If a required catalog is empty, do not invent a create
command. Explain that the resource must be configured through another supported
surface and ask before switching interfaces.

## Runs and results

| Stage | CLI command | Required IDs or output |
| --- | --- | --- |
| Start | `lightsage eval-runs create` | Takes eval, configuration, and agent IDs; returns an eval-run ID. |
| List jobs | `lightsage eval-runs list` | Returns lifecycle state and progress. |
| Poll one job | `lightsage eval-runs retrieve` | Takes the eval-run ID. Poll until a terminal status. |
| List outcomes | `lightsage eval-results list` | Returns completed results and their result IDs. |
| Inspect outcome | `lightsage eval-results retrieve` | Takes a result ID, not an eval-run ID. |

Starting an eval run consumes credits. Progress may reach 100 percent before
the parent status is terminal, so use the run's status to decide when polling is
complete.

## Typical ID flow

```text
evals list
  → eval ID
  → evals configurations list
  → configuration ID

agents list
  → agent ID

eval ID + configuration ID + agent ID
  → eval-runs create
  → eval-run ID
  → eval-runs retrieve

eval-results list
  → result ID
  → eval-results retrieve
```

For every flow, list before guessing, match on stable fields, and retrieve the
selected resource when identity affects a write or destructive action.
