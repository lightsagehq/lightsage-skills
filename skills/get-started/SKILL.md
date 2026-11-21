---
name: get-started
description: Set up and orient a new Lightsage plugin user. Use when the user has just installed or connected Lightsage, asks what the plugin can do, asks how to get started, or when another Lightsage skill cannot proceed because the Lightsage connection is missing or unauthenticated. Do not use to analyze prompt runs or eval runs once the connection works.
---

# Get started with Lightsage

Confirm the Lightsage connection works, then point the user at the workflow
that fits what they want to do. Keep it short: one check, one recommendation.

## Confirm the connection

Use the connected Lightsage MCP capability to check the user's Lightsage auth
status.

- If it returns the user's account and organization, say which organization
  the connection uses and continue.
- If the capability is unavailable or unauthenticated, tell the user to
  connect Lightsage and sign in with their Lightsage account, then stop. Do
  not fabricate data or switch to another interface without being asked.
- If the user belongs to several organizations and the wrong one is
  connected, tell them to connect again and choose the right organization.
  Connecting again replaces the organization the existing connection uses.

## Point to the right workflow

Ask what the user wants to do if they have not said, then hand off:

- **Understand how AI assistants and coding agents talk about their brand** —
  mentions, recommendation position, sentiment, and citations in stored
  prompt runs. Use `from-prompt-runs-to-actions`.
- **Find out why an eval failed or regressed and what to change** — use
  `from-eval-runs-to-actions`.
- **Work from a terminal, a shell script, or CI** — point the user to the
  Lightsage CLI documentation at https://lightsage.com/docs, and only when they
  explicitly ask for the command line.

If the organization has no prompt runs or eval runs yet, say so plainly and
tell the user to set them up in the Lightsage dashboard at
https://app.lightsage.com before running an analysis.
