# Intent and recovery

Use this reference when the CLI action may not match the user's intended
effect, or when a failure blocks normal execution.

## Act on clear intent

- Run relevant reads directly.
- A clear request to create, update, generate content, start an eval run, or
  delete exact items authorizes that matching action. Do not reconfirm it.
- Inspect current state first when identity or existing configuration matters.
- Use `--dry-run` to validate a write when useful. Continue without pausing if
  the serialized request matches the user's intent.
- Clarify when the target is ambiguous, required information is missing, the
  command has materially different consequences, or the action would broaden
  the request. Never replace archive or disable intent with permanent deletion.

## Recover without guessing

**Authentication:** Inspect configuration with `lightsage auth whoami` and
validate access with `lightsage status auth-status-get`. If credentials are
missing, direct the user to the interactive `lightsage auth login` flow. Never
request or expose the key value.

**Empty catalog:** State what is empty and which dependent action cannot
continue. Offer the smallest supported setup step. If the CLI only lists that
resource type, do not invent a create command or silently switch interfaces.

**Unknown command:** Record `lightsage version`, find the path with
`lightsage --usage`, then inspect help for the verified command. Follow the
installed binary when documentation differs.

**Validation or service error:** Check help and dry-run serialization. Retry an
idempotent read once after a transient failure. Do not retry an uncertain write
until list or retrieve proves it did not take effect.

## Verify the outcome

Use the returned resource and a retrieve or list operation when available.
Report whether the action was executed or previewed, the affected resource ID,
the observed final state, and any remaining blocker. A successful exit code
alone is not proof when the resulting state can be checked.
