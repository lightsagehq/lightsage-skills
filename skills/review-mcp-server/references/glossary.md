# MCP server review glossary

Use these terms in findings so a defect names its fix. Each row says what good and bad look like.

| Term | Meaning | Good | Bad |
|---|---|---|---|
| Tool surface | What `tools/list` shows a caller | About 20 job-level tools plus a discovery tool for the long tail | The full REST API mirrored on every client |
| Granularity | How much one tool does | `schedule_event`: one intent, chaining done inside | `manage_user` with a `mode` argument |
| Intent-level tool | Maps to a user goal | `deploy_project`, `track_latest_order(email)` | `create_deployment` plus three siblings the model must chain |
| Atomic tool | One function, no inside branching on required arguments | `create_user` needs `email`; `delete_user` needs `id` | One tool whose required fields change with `action` |
| Namespacing | Grouping that prevents collisions across servers | `asana_projects_search` | `vendor_mixed_people_api_search`, which leaks API terms |
| Selection copy | The text the model chooses by: name, title, description | "Use this when the user asks for overdue invoices. Not for reminders." | "Get server logs." |
| Human-readable title | The `title` shown to users in approval prompts and listings | "Search invoices" | Empty, or the snake_case name repeated |
| Flat schema | Typed top-level arguments | A `status` enum and a default `limit` | `filters: dict`, deep `oneOf`, a `request` wrapper object |
| Server instructions | Cross-tool guidance sent at `initialize` | Short, global, per topic ("all dates are UTC; IDs are strings") | Repeating every description; telling the model which tools to always call |
| Context bloat | Tokens spent on definitions and results | Code mode or discovery keeps definitions near 1,000 tokens for thousands of endpoints | A reorder tool that returns the whole 100K-token dashboard |
| Progressive discovery | Revealing tools on demand | Host tool search; category words in a `discover` tool's description | Blind search that misses the words users say |
| Code mode | The model writes code that runs in a sandbox against the API | Filter 2,000 rows, return 3 | One simple lookup routed through a sandbox |
| Response shaping | Controlling fields and size of results | `response_format` or `fields`; pagination with a next step | 50 fields when 5 decide; no `limit` |
| Stable identifier | Safe across tools and time | `LIN-123`; string IDs; a canonical `url` | Rotating UUIDs; 10+ digit IDs sent as numbers (models round them) |
| Actionable error | Says what to do next | "Invalid date: must be in the future (got 2025-01-01)", with `isError: true` | "Error 500"; a bare "no results" |
| Tool annotations | `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` | Explicit and truthful on every tool | Omitted (clients assume destructive), or a read tool marked destructive |
| Generic executor | One tool that runs any operation (`execute`, `api_request(method, path)`, `call_tool(name)`) | Not present; each operation is its own reviewed tool | Present; banned or flagged by all three directories |
| Prompt-injection pattern | Model-facing text that steers behavior beyond the tool's job | Describes what the tool does and when to use it | "Always call this first", "ignore other tools", "fetch rules from <url>" |
| Golden prompt set | Labeled selection tests | Direct, indirect and negative prompts, with a held-out share | Direct prompts only, written by the tool's author |
| Handle | A job ID returned for slow work | Returns `{run_id, status}` in under 5 seconds; a status tool polls | Holds the request open for minutes |

## Words that sound alike

- **Title vs name**: the name is the identifier the model calls; the title is for people. Claude's directory requires both.
- **Read-only vs non-destructive**: read-only changes nothing. Non-destructive changes state but only adds (create a draft). Queuing a job is neither read-only nor, usually, destructive.
- **Open world vs external host**: `openWorldHint` is about touching public or arbitrary destinations (web search, posting publicly), not about your API being hosted elsewhere.
