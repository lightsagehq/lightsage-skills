<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/lightsage-logo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/lightsage-logo.svg">
  <img alt="Lightsage" src="./assets/lightsage-logo.svg" width="120">
</picture>

# Lightsage Skills

Skills that show whether AI agents pick, cite and can use your product, and what to fix when they don't. They follow the [Agent Skills](https://agentskills.io) format and install as one plugin for Claude Code, Codex and ChatGPT, Cursor, Grok, and any [Agent Plugins](https://agent-plugins.org) client.

Most skills work without a Lightsage account: they use the coding agents, logs and site you already have. Connect Lightsage to run the same jobs across more agents, on a schedule, and act on the results.

## Install

### Full plugin

Install the complete plugin to add all skills and the hosted Lightsage MCP
server. The open skills never call the server; you only sign in to Lightsage
when you use a skill that needs a workspace.

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

Install skills without the hosted MCP server (the open skills need nothing else):

```bash
npx skills add lightsagehq/lightsage-skills
```

Choose the skills and supported agents you want when prompted.

## Available Skills

### Open skills (no account needed)

| Skill | Use it to |
|---|---|
| [`test-agent-pick`](./skills/test-agent-pick) | Find out whether Claude Code, Codex and other coding agents pick you or a competitor for unbranded developer tasks, and why |
| [`test-api-on-agents`](./skills/test-api-on-agents) | Check whether coding agents can finish real tasks with your API, MCP server, CLI or SDK, and where they get stuck |
| [`audit-agent-readiness`](./skills/audit-agent-readiness) | Fetch your site and docs as each AI crawler and agent to find blocks, empty pages and missing markdown, then rank the fixes |
| [`measure-ai-visibility`](./skills/measure-ai-visibility) | Measure how often ChatGPT, Claude, Perplexity, Gemini and coding agents mention, recommend and cite you, with sample sizes |
| [`read-agent-traffic`](./skills/read-agent-traffic) | Read your server or CDN logs to see which AI agents and bots visit, what they read and where they hit errors |
| [`review-mcp-server`](./skills/review-mcp-server) | Review an MCP server's tools against six pass/fail criteria and the ChatGPT, Claude and Google directory rules |

Each open skill ends with what to run in Lightsage when a workspace is connected.

### Lightsage workspace skills

| Skill | Use it to |
|---|---|
| [`track-agent-pick`](./skills/track-agent-pick) | Set up and read Agent Preference evals: are you winning against a competitor on coding agents this week? |
| [`fix-ai-answers`](./skills/fix-ai-answers) | Turn prompt-run evidence (missing mentions, wrong claims, competitor wins) into ranked, verifiable fixes. Also works on answers you paste in |
| [`fix-failed-evals`](./skills/fix-failed-evals) | Diagnose failed or regressed eval runs and propose the smallest fix with a verification plan |
| [`lightsage-cli`](./skills/lightsage-cli) | Operate Lightsage from a terminal, script or CI job |

Without a workspace, each of these points you to its open counterpart.

## MCP Server

The plugin registers Lightsage's hosted MCP server at `https://mcp.lightsage.com/mcp` (streamable HTTP). Only the workspace skills use it. It authenticates with OAuth, and compatible clients guide you through sign-in the first time a skill needs it.

## Plugins

This repository follows the [Agent Plugins](https://agent-plugins.org) open standard, with `plugin.json` and `mcp.json` at the root and skills in `skills/`. Any conformant client can load it.

It also includes platform-specific plugin metadata:

- **OpenAI and Codex** — `.codex-plugin/` and `.agents/plugins/marketplace.json`
- **Claude Code** — `.claude-plugin/`
- **Cursor** — `.cursor-plugin/`
- **Grok** — `.grok-plugin/`

## Prerequisites

- **Open skills:** Python 3 for their scripts. `test-agent-pick` and `test-api-on-agents` run the coding-agent CLIs you have installed (`claude`, `codex`) on your own subscription; `measure-ai-visibility` uses those CLIs or API keys you set in your shell.
- **Workspace skills:** a Lightsage account with access to a workspace. The `lightsage-cli` skill also needs the Lightsage CLI installed and signed in.

Skills that start many agent sessions or Lightsage runs show what they will run and wait for your yes first. Lightsage runs use usage-based credits.

## Testing the skills

`evals/run_triggers.py` checks that each skill loads for the requests it should handle and stays out of near-misses, using the prompts in `skills/*/evals/evals.json`. Every session runs in a throwaway project with no user settings, memories or other skills.

```bash
python3 evals/run_triggers.py --harness claude --runs 3
python3 evals/run_triggers.py --harness codex --runs 3
```

## Privacy and support

The open skills run on your machine. They call the agents, sites and APIs you point them at, and send nothing to Lightsage.

The workspace skills connect to Lightsage's hosted MCP server or CLI and send the arguments needed for the requested workspace operation. The server can read and change workspace data through the signed-in user's account. The skills read existing evidence by default; they create tasks, start runs or change data only after you confirm.

See the [Lightsage Privacy Policy](https://lightsage.com/privacy) for data
collection, usage, and retention. For setup help or product and security
concerns, contact [support@lightsage.com](mailto:support@lightsage.com).

## License

MIT
