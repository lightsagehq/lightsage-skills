# Measuring selection, result size and errors

Read this before claiming a pass on criteria 2, 4 or 5. Every number in a report needs its n and the host it was measured on.

## Criterion 2: does the right tool get picked?

Build a golden prompt set from the callers' top jobs:

- **Direct** prompts use the product's or tool's words ("search my invoices for overdue ones").
- **Indirect** prompts state the need without them ("who still owes us money from March?"). These are where selection fails.
- **Negative** prompts share keywords but should not trigger the server, or should trigger a different tool ("remind me to chase invoices on Friday" for a server with no reminders).
- Label each prompt with the expected tool (or "none"). Keep 30 to 40% of the set held out and don't tune descriptions against it.
- Aim for 20 or more prompts per server, at least 5 negatives, and every pair of similar tools covered.

Run it:

- At least 3 runs per prompt per host, 5+ before a ship decision. Hosts vary run to run; one pass proves nothing.
- Use at least Claude (or Claude Code), ChatGPT and one coding agent if those are target surfaces.
- Clean sessions: no memories, no other connectors that could win the call, no project instructions that name the tools. A user's own AGENTS.md or connectors silently change the result.
- Score the first tool call only. Record: expected tool, actual tool (or none), arguments valid yes/no.

Report:

- Recall = right tool called on prompts that expect one. Negative precision = no call (or the right other tool) on negatives. Confusion = share of prompts where tool A was called but B was expected, per pair.
- Give rates with n ("recall 17/20 = 85% on Claude, 3 runs each"), split direct, indirect and negative.

Running many hosted sessions costs the user time or credits. Say how many sessions the set implies (prompts x runs x hosts) and get a yes first.

## Criterion 4: are results cheap and self-describing?

Only on a server you own, or with the owner's yes.

- Call each top job once with realistic arguments; also call the widest list with defaults.
- Tokens ~ characters / 4 of the serialized result content. Note p50 and the largest.
- Check each result: does every metric say its unit, window and sample size? Do sources carry a `url`? Does an empty result say why ("no invoices overdue since 2026-03-01") instead of `[]`? Are there trace IDs, internal account IDs or PII the request didn't need?
- Without permission to call, read response schemas or docs and mark sizes "estimated from schema".

## Criterion 5: do failures teach?

- Send one invalid argument per top tool (a past date, a bad enum, a missing ID) on your own server. Expect `isError: true` and text that says what to change.
- Ask for logs or analytics: tool error rate by client. Under about 3% from outside clients is a reasonable bar; above it, group errors by tool and message.
- Check that retries of a write after a timeout don't create duplicates (idempotency key or a lookup before create).

## What to say when you couldn't measure

"Not measured: no permission to call tools" or "Not measured: needs a selection run on ChatGPT (est. 120 sessions)". Never fill a gap with a typical number from another server.
