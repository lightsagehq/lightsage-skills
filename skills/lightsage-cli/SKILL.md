---
name: lightsage-cli
description: Operate and troubleshoot Lightsage from a terminal, shell script, or CI workflow. Use only when the user explicitly asks for the `lightsage` CLI, command-line execution, scripting, or CI/CD. Do not use for outcome analysis that can be completed through a connected Lightsage MCP capability.
---

# Lightsage CLI

Use the installed CLI to carry out the user's Lightsage task accurately and
safely. Teach CLI mechanics; leave goal-oriented journeys to workflow skills.

## Operating loop

1. Understand the user's intended outcome.
2. Check only the prerequisites needed, then discover the current command and
   flags from the installed binary.
3. Resolve real resource IDs and execute the action when it matches the user's
   intent. Preview writes when useful.
4. Verify the outcome and report the important IDs or blockers.

## Establish readiness

- Run `lightsage version` before giving version-sensitive commands.
- Use `lightsage auth whoami` to inspect credential configuration; it masks
  credential values. Use `lightsage status auth-status-get` when the task
  requires validating the credential against the service.
- If `lightsage` is unavailable, stop and direct the user to the current
  Lightsage CLI documentation. Do not invent or reuse an unverified installer.
- Do not print, persist, or pass API keys on the command line. Prefer the
  interactive login or the customer's existing secret-management mechanism.

## Discover commands from the binary

Treat the installed binary as the authority for command names and flags:

1. Run `lightsage --usage` to inspect the complete command tree.
2. After confirming that a command exists, run
   `lightsage <command-path> --help` for its flags and accepted values.
3. Use `--dry-run` to verify how a write serializes before sending it.
4. Use the published documentation for concepts and examples, not to override
   the installed command surface.

When the docs and binary disagree, state the installed version and follow
the binary.

## Understand the resource model

```text
Topic → Prompt → Prompt run
Opportunity    Task    Site audit    Draft → Final content

Eval subject + Configuration + Agent → Eval run → Eval result
               ├── Repository
               ├── Environment
               ├── CLIs and skills
               ├── MCP servers
               └── Docs
```

Run IDs and result IDs are different: poll with the run ID and inspect the
outcome with the result ID. The resources from `lightsage skills list` are
reusable Lightsage context packages, not local Agent Skills such as this one.

Treat all IDs as opaque. List the relevant catalog, match on stable fields, and
retrieve the selected resource when identity matters. If multiple resources
match, ask the user to choose. If the catalog is empty, report the missing
prerequisite instead of inventing an ID.

Read [references/resource-model.md](references/resource-model.md) when choosing
the command for a resource, following IDs between resources, or determining
which catalogs are read-only in the current CLI.

## Execute predictably

- Use long command names in commands shown to the user; do not use generated
  aliases.
- Prefer `--output-format json` for programmatic inspection and `table` for a
  compact human inventory. Use `--jq` only after confirming the response shape.
- Treat `--jq` output as JSON rather than assuming it is raw shell text.
- Repeat list-valued flags once per value unless the current help or dry run
  demonstrates another representation.
- Prefer individual flags for short requests. Use `--body` or stdin when a
  structured payload is clearer or avoids fragile shell quoting.
- Add `--no-interactive` in automation when a prompt or explorer would block.

Read [references/command-patterns.md](references/command-patterns.md) for
verified examples of discovery, output handling, ID chaining, repeated flags,
and write previews.

## Follow the user's intent

- Perform read-only inspection directly when it is within the user's request.
- A clear request to create, update, run a credit-consuming operation, or delete
  exact items authorizes that matching action. Do not ask for redundant
  confirmation.
- Inspect relevant state and use `--dry-run` when it helps validate a write,
  but continue without interrupting the user when the serialized action still
  matches the request.
- Clarify only when the target is ambiguous, required information is missing,
  the CLI action has materially different consequences, or execution would
  expand beyond the requested scope.
- Never substitute permanent deletion when the user asked for a reversible
  archive, disable, or removal from one configuration.
- Never retry a write whose outcome is uncertain until current state proves
  that the first attempt did not take effect.

Read [references/safety-and-recovery.md](references/safety-and-recovery.md)
when action semantics may differ from the user's intent or when authentication,
empty state, validation, or service failures block the task.

## Finish with evidence

After an operation, state what was inspected or changed, the relevant resource
ID, and how success was verified. If blocked, name the missing prerequisite and
the smallest safe next step. Do not claim success from a dry run or from an exit
code alone when the resource can be retrieved and verified.

## Boundaries

This skill covers CLI operation across Lightsage product areas. It does not
choose prompts, judges, models, growth priorities, or end-to-end onboarding
journeys. It does not silently fall back to the public API, MCP, dashboard, or
private Lightsage procedures when the CLI lacks an operation. Explain the
boundary and ask before changing interfaces. Keep outcome-oriented prompt-run
and eval-result reasoning in their dedicated skills; this skill supplies CLI
mechanics only when the request explicitly selects a command-line workflow.
