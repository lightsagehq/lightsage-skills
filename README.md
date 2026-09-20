<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/lightsage-logo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/lightsage-logo.svg">
  <img alt="Lightsage" src="./assets/lightsage-logo.svg" width="120">
</picture>

# Lightsage Skills

A collection of skills for AI coding agents following the [Agent Skills](https://agentskills.io) format. Available as a plugin for OpenAI, Claude Code, Cursor, Grok, and any [Agent Plugins](https://agent-plugins.org) client. Includes Lightsage's hosted MCP server for tool access.

## Install

### Full plugin

Install the complete plugin to add all Lightsage skills and the hosted
Lightsage MCP server. Your client will prompt you to authenticate with
Lightsage on first use.

#### ChatGPT and Codex

```bash
codex plugin marketplace add lightsagehq/lightsage-skills
codex plugin add lightsage@lightsage-skills
```

Restart Codex or begin a new session after installation.

#### Claude Code

```bash
claude plugin marketplace add lightsagehq/lightsage-skills
claude plugin install lightsage@lightsage-skills
```

#### Cursor

For local installation:

```bash
mkdir -p ~/.cursor/plugins/local
git clone https://github.com/lightsagehq/lightsage-skills.git ~/.cursor/plugins/local/lightsage
```

Restart Cursor or run **Developer: Reload Window**, then open **Customize** to
confirm that the Lightsage skills and MCP server were loaded.

#### Grok Build

```bash
grok plugin marketplace add lightsagehq/lightsage-skills
grok plugin install lightsage@lightsage-skills
```

You can also open `/plugins` and install Lightsage from the Marketplace tab.

### MCP only

Connect a remote Streamable HTTP MCP server named `lightsage` using:

```text
https://mcp.lightsage.com/mcp
```

Your client will prompt you to authenticate with Lightsage. This provides the
MCP tools without installing the skills in this repository.

### Skills only

Install selected Lightsage skills without the hosted MCP server:

```bash
npx skills add lightsagehq/lightsage-skills
```

Choose the skills and supported agents you want when prompted.

## Available Skills

| Skill | Description |
|---|---|
| [`from-prompt-runs-to-actions`](./skills/from-prompt-runs-to-actions) | Turn prompt visibility evidence, mentions, sentiment, and citations into prioritized actions |
| [`from-eval-runs-to-actions`](./skills/from-eval-runs-to-actions) | Diagnose eval outcomes and execution evidence, then propose focused fixes and validation runs |
| [`lightsage-cli`](./skills/lightsage-cli) | Operate Lightsage from the terminal |

## MCP Server

The plugin registers Lightsage's hosted MCP server at `https://mcp.lightsage.com/mcp` (streamable HTTP), giving agents access to prompt runs, evals, and other workspace data. It authenticates via OAuth, and compatible clients guide you through sign-in when they first connect.

## Plugins

This repository follows the [Agent Plugins](https://agent-plugins.org) open standard, with `plugin.json` and `mcp.json` at the root and skills in `skills/`. Any conformant client can load it.

It also includes platform-specific plugin metadata:

- **OpenAI and Codex** — `.codex-plugin/` and `.agents/plugins/marketplace.json`
- **Claude Code** — `.claude-plugin/`
- **Cursor** — `.cursor-plugin/`
- **Grok** — `.grok-plugin/`

## Prerequisites

- A Lightsage account with access to a workspace
- The Lightsage CLI installed and authenticated when using the `lightsage-cli` skill

## License

MIT
