# Lightsage Agent Skills

Agent Skills for working with [Lightsage](https://lightsage.com), the Agent
Experience Platform for developer tools. These skills help AI coding agents
operate the Lightsage CLI and turn prompt and eval runs into concrete actions.

## Available skills

| Skill | Use it for |
| --- | --- |
| [`lightsage-cli`](skills/lightsage-cli/SKILL.md) | Operating and troubleshooting the Lightsage CLI, including authentication, command discovery, resource IDs, writes, and recovery. |
| [`from-prompt-runs-to-actions`](skills/from-prompt-runs-to-actions/SKILL.md) | Turning stored prompt visibility evidence, mentions, sentiment, and citations into prioritized actions. |
| [`from-eval-runs-to-actions`](skills/from-eval-runs-to-actions/SKILL.md) | Diagnosing eval outcomes and execution evidence, then proposing targeted fixes and validation runs. |

## Install

Install the repository with an Agent Skills-compatible client:

```bash
npx skills add lightsagehq/lightsage-skills
```

The installer will prompt you to choose the skills and supported agents.

You will also need the Lightsage CLI and an authenticated Lightsage workspace.
Follow the [Lightsage documentation](https://lightsage.com/docs) for the current
CLI installation and authentication steps.

## Use

Ask your coding agent for the outcome you want. The relevant skill can be
selected automatically by clients that support Agent Skills.

Examples:

- "Use the Lightsage CLI to show my recent eval results."
- "Review this week's prompt runs and recommend the three highest-impact
  actions."
- "Diagnose the latest failed eval and propose the smallest useful fix."

The `lightsage-cli` skill supplies shared CLI mechanics. The two workflow
skills use those mechanics to analyze evidence and recommend or perform the
actions requested by the user.

These Agent Skills are installed in your coding agent. They are different from
the reusable Lightsage resources returned by `lightsage skills list`.

## Compatibility

The initial command examples were verified against Lightsage CLI 0.6.7, built
2026-09-06. The skills inspect the installed binary before relying on
version-sensitive commands, so later CLI changes fail clearly instead of using
stale syntax.

## License

Licensed under the [MIT License](LICENSE).
