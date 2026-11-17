# Directory rules that change the verdict

Checked 2026-11-17 against the sources listed at the end. These pages change often: re-read the source before telling a user a rule is current, and say the date you checked.

## Contents

- Rules all three share
- Claude Connectors Directory
- ChatGPT and Codex plugin directory (OpenAI)
- Google Connected Apps (Gemini, AI Mode in Search)
- Where the directories disagree
- Sources

## Rules all three share

- No generic executors. Each operation is its own tool with its own schema and hints.
- Hints must match behavior. Wrong hints are a top rejection reason everywhere.
- Descriptions say what the tool does; they must not steer the model toward or away from other tools or pull instructions from elsewhere.
- A working, populated reviewer account with no MFA, and example prompts that pass.

## Claude Connectors Directory

Submitted at claude.ai/directory/manage. Anthropic scans automatically and lists as Community by default; some servers get escalated to Verified, where a person runs each tool.

- **Annotations:** every tool has a `title` and the applicable `readOnlyHint` or `destructiveHint`. The portal flags tools missing them. These drive auto-permissions: read-only tools can run without confirmation, destructive ones always prompt.
- **Read and write split:** a tool that accepts both safe (GET) and unsafe (POST, PUT, PATCH, DELETE) methods is rejected, even if the description documents which is which. Split into a read tool and create, update, delete tools.
- **Custom query tools** (caller builds the path, query or body) must name or link the target API in the description.
- **Names** 64 characters or fewer.
- **Descriptions** are rejected if they tell Claude to call software the user didn't ask for, interfere with Claude calling other tools, pull behavioral instructions from external sources, hide or encode instructions, or promote products.
- **Functional quality:** every tool succeeds with valid input; "Internal Server Error" or "Bad Request" with no detail fails; responses sized to the request; no reading Claude's memory, chat history or user files.
- **First-party APIs:** the server calls your own APIs (or ones you may proxy), on a domain that matches your service.
- **Not accepted:** moving money or crypto; AI image, video or audio generation.
- **Auth:** OAuth 2.0 for user data, or none for public data. Claude sends S256 PKCE on every authorization request; advertise `code_challenge_methods_supported: ["S256"]`. Register via DCR or CIMD (CIMD needs `client_id_metadata_document_supported: true` and `none` in `token_endpoint_auth_methods_supported`). Return `401` with `WWW-Authenticate: Bearer resource_metadata="..."`. Claude uses only the first `authorization_servers` entry. Accept `https://claude.ai/api/mcp/auth_callback` and loopback redirects on any port for Claude Code. Rotate refresh tokens for public clients; return `invalid_grant` when one is dead. Discovery and token endpoints must answer within 10 seconds.
- **Submission materials:** credentials for a fully populated test account; up to 3 use cases with example prompts that work (practitioners report reviewers expect at least 3); public docs by the publish date (a help article is enough); privacy policy, support contact, icon. MCP Apps add 3 to 5 PNG screenshots at least 1000px wide.

## ChatGPT and Codex plugin directory (OpenAI)

Submitted as a plugin through the OpenAI Platform dashboard, after identity or business verification for the publishing name.

- **One tool per operation:** "Expose each model-callable operation as a separate tool." Discovery, operation selection or schema fetching with a generic executor is not allowed.
- **Tool independence:** a tool must not tell the model to invoke another plugin or connector.
- **Fair play:** no model-readable text (descriptions, titles, annotations) that makes the model prefer this plugin or disparages others; no "overly broad triggering".
- **Hints:** `readOnlyHint`, `destructiveHint` and `openWorldHint` as explicit booleans on every tool. Read-only means no external state change: starting jobs, queuing work, writing logs or uploading files are writes. Destructive covers delete, overwrite, cancel, revoke, irreversible sends; "can be undone" doesn't make it non-destructive. `openWorldHint` is true for public or arbitrary destinations, false for a bounded private workspace.
- **Scan and rescan:** "Scan Tools" imports names, titles, descriptions, schemas, annotations and server `instructions` into the draft. Justification text never overrides the advertised hint: fix the server, redeploy, rescan. After publishing, OpenAI rescans periodically; new tools are hidden and changed tools keep the old definition until they pass automated checks; deleted tools vanish at once.
- **Minimal inputs and outputs:** no fields that request conversation history or "just in case" context; responses carry no session, trace or request IDs, timestamps or PII the request didn't need.
- **Test cases:** test prompts with expected responses; every one must pass on ChatGPT and Codex surfaces. Reviewer login must work with no MFA or extra signup.
- **Names:** don't append "MCP" or "Plugin" to the product name; no pricing or upsell in descriptions.

## Google Connected Apps (Gemini, AI Mode in Search)

- **Surface size:** servers "exposing dozens of tools or deeply nested 'mega-tool' schemas will be flagged during review for fixes." No number is given.
- **Atomic tools:** one function each, no inside conditions; `manage_user` with create/update/delete is the named anti-pattern. Deep nesting or `oneOf`/`anyOf` means the tool is too broad.
- **Static tools only:** every callable operation is declared at registration. No dynamic discovery (`list_tools`, `get_schema`) and no generic runtime dispatchers (`execute_command`, `invoke_dynamic_tool`). Omit health checks, setup routines and admin helpers from `tools/list`.
- **No steering:** apps must not "reference other tools or create new rules for when or how other tools should be used", use broad descriptions to get picked over other apps, or "return system instructions through app responses" (all instructions must be present at ingestion).
- **Server instructions are required:** registration fails with "Your MCP server does not have instructions" when `initialize` returns no `instructions`. They are added to the system prompt: describe what the server is for, don't list features or repeat descriptions.
- **No agent-to-agent:** the app must not proxy for or talk to other autonomous AI agents.
- **No API wrappers:** repackaging third-party APIs you don't own is prohibited.
- **Backend aggregation:** filter and summarize on the server; never return raw rows or logs. Send long numeric IDs as strings.
- **Protocol and transport:** Streamable HTTP only (no legacy SSE); MCP spec up to `2025-11-25`; use a versioned path (`/mcp/v1`) and add `/mcp/v2` for breaking changes. A stateless server may answer `GET` with `405`.
- **Annotations:** tools that alter persistent state, modify or delete data, change access or move money need `destructiveHint: true` (or a console confirmation setting). `openWorldHint: true` also triggers confirmation. Declare `readOnlyHint: true` on queries; omitted hints default to the worst case.
- **Data minimization:** never request prompts, full conversation context or history.

## Where the directories disagree

- **Naming other tools in descriptions:** Google's optimization guide recommends saying where an argument comes from ("from the `order_search` tool"), while Google's policy bars referencing other tools and Claude rejects text that interferes with calling other tools. Safest: describe the argument ("the order `id` returned by a search") without naming or ordering other tools; flag any "always/never/first call" text as a blocker.
- **`destructiveHint` on additive writes:** OpenAI allows `false` for purely additive writes; Google wants `true` on any persistent state change. Claude uses the hint for auto-permissions. One server may need per-host hint choices or confirmation settings.
- **Refresh tokens:** Claude asks public clients to rotate refresh tokens; check each host's current guidance before changing rotation for one of them.
- **Server instructions:** Google requires them; Claude and OpenAI import them but don't require them. Keep them short so they help everywhere.
- **App mentions:** Google normalizes `@AppName` triggers; other hosts ignore them. Don't rely on mentions in example prompts.

## Sources

- Claude: https://claude.com/docs/connectors/building/review-criteria, https://claude.com/docs/connectors/building/submission, https://claude.com/docs/connectors/building/authentication
- OpenAI: https://developers.openai.com/plugins/plugin-guidelines, https://developers.openai.com/apps-sdk/deploy/app-review
- Google: https://developers.google.com/connected-apps/mcp/server-optimization, https://developers.google.com/connected-apps/connected-apps-policy (updated 2026-11-02), https://developers.google.com/connected-apps/gpc/troubleshooting
