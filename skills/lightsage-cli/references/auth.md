# Authentication

The CLI resolves one credential, the Lightsage API key, from four sources.

## Precedence

The CLI checks these in order and uses the first that resolves:

1. **Flag** — `--lightsage-api-key-auth <key>` on the command
2. **Environment variable** — `CLI_LIGHTSAGE_API_KEY_AUTH`
3. **OS keychain** — written by `lightsage auth login`
4. **Config file** — `~/.config/lightsage/config.yaml`

An environment variable therefore overrides a stored keychain entry. If a
command authenticates as the wrong organization, check the environment before
anything else.

## Environment variables

`CLI_LIGHTSAGE_API_KEY_AUTH` is canonical. Two aliases are accepted and
resolve in this order when the canonical name is unset:

1. `LIGHTSAGE_API_KEY`
2. `CLI_API_KEY`

The `CLI_` prefix is the CLI's general environment convention: any global flag
maps to `CLI_` plus the flag name in upper snake case.

## Authenticate in CI and agent environments

Set the environment variable and pass `--no-interactive` on every command.
Without it, a missing credential opens a prompt and the command hangs:

```bash
export CLI_LIGHTSAGE_API_KEY_AUTH="<key>"
lightsage status auth-status-get --no-interactive
```

## Authenticate locally

Run `lightsage auth login` to store the key in the OS keychain, or
`lightsage configure` to set credentials and preferences together. Use
`lightsage auth logout` to remove a stored key.

## Verify a credential

Two commands answer different questions.

`lightsage whoami` reports what the CLI resolved and from where, without
calling the API. The key is masked and the source is named:

```
Credentials:
  --lightsage-api-key-auth    [keyring] ls******cQ
```

`lightsage status auth-status-get` calls the API and proves the key works:

```json
{"authenticated":true,"org_id":"…","api_key_id":"…",
 "scopes":["read","write","jobs:read","jobs:run","jobs:cancel"]}
```

Use `whoami` to debug which source won. Use `auth-status-get` to confirm the
key is valid and to read the organization it belongs to.

`lightsage status get` is not an authentication check. It is an
unauthenticated liveness probe that returns `{"status":"ok"}` whether the key
is valid, invalid, or absent.

## Handle keys safely

Create keys in the dashboard under **Settings > API Keys**. A key is shown
once. Never commit one, and never paste one into a command that gets logged —
prefer the environment variable, which keeps the value out of shell history.

The `jobs:cancel` scope appears in `auth-status-get` output, but no command
cancels a run.
