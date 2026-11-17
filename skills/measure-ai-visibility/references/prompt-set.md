# Building the prompt set

The prompt set decides what the numbers mean. A set full of glossary questions reports healthy visibility while you lose every shortlist.

## Contents
- Start from the decision
- Where real phrasing comes from
- The five intents
- Writing rules
- Size and balance
- Controls
- Versioning
- Worked example

## Start from the decision

Write one sentence about what the numbers will decide before writing any prompt: "Are we on the shortlist when a US seed-stage SaaS team asks for an email API?" or "Did the pricing-page rewrite fix what answers say about our free tier?" Drop every prompt that cannot move that decision.

## Where real phrasing comes from

In order of preference:
1. What buyers say they asked an AI (a "what did you ask ChatGPT?" field on signup or in sales calls).
2. Sales call notes, demo requests, support tickets, objections.
3. Community threads where buyers ask for recommendations (Reddit, Hacker News, Stack Overflow, Slack and Discord communities), copied close to verbatim.
4. Search queries from Search Console or a keyword tool, rewritten the way someone types into a chat box. "crm small business" becomes "What CRM should a 5-person agency that lives in Gmail use?"

Do not turn a keyword list into questions mechanically. Chat prompts are longer and carry context, and that context changes which sources get retrieved.

## The five intents

| Intent | Shape | Example (fictional category: transactional email) |
|---|---|---|
| category | "What are the best X for Y?" | "What's the best transactional email API for a small SaaS on Node?" |
| problem | The pain, no category word | "Our password reset emails keep landing in spam. What should we use instead?" |
| comparison | Two or three named competitors, not you | "Postbird vs Sendly for a startup sending 50k emails a month?" |
| alternatives | "Alternatives to <competitor>" | "Good alternatives to Postbird that are cheaper at low volume?" |
| control | Names you | "What is Acme Mail?" |

Weight toward category and problem prompts: they show whether you make the shortlist unprompted. Comparison and alternatives prompts show whether you get pulled into a decision you were not named in.

For a devtool, add developer-phrased prompts that a coding agent would get: "How do I send email from a Next.js app?", "Which library should I use for X in Python?". Run those on `claude-code` and `codex` as well as the answer engines.

## Writing rules

- Never name your brand outside controls. "Is Acme good for X?" measures recall of a name you supplied, not visibility.
- One intent per prompt. Split "best X and how much does it cost" into two.
- Add the context a real buyer adds: team size, stack, budget, region, a constraint ("we need EU data residency").
- Keep wording neutral. "What's the cheapest…" is fine if buyers ask it; "Which tool beats Postbird…" leads the answer.
- No answer-format instructions ("list 5 tools with pros and cons"). They change which brands appear.
- Collapse paraphrases of the same intent into one prompt. Add wording variants only if you are testing wording sensitivity, and tag them.
- Match the language and country of the market you are measuring. A German prompt is a separate measurement, not a variant.

## Size and balance

- 15–40 prompts. Under 15, one odd prompt swings the rate. Over 40, the run gets expensive before you know the set works.
- At least 3 prompts per intent you report on separately.
- 3 runs per prompt per engine for a baseline, 5 for a before/after decision. Past 5 runs, more prompts reduce uncertainty more than more runs.
- First pass: `--limit 3` on one engine, read the answers, fix prompts that get refused or misread, then run the full set.

## Controls

Add 1–2 prompts that name you ("What is Acme Mail?", "Acme Mail pricing"). `tally.py` keeps them out of the rates and lists them separately. If a control comes back "NOT named", the extraction is wrong (missing alias, case-sensitive name) or the engine does not know you at all; both are findings to fix before reading any rate.

## Versioning

Save the set as `prompts-YYYY-MM-DD.csv` and never edit it in place after a run. When you change the set, compare periods only on the prompts both versions share. Keep engines, models and country the same between periods, or say which changed.

## Worked example

```csv
id,intent,prompt
p01,category,What's the best transactional email API for a small SaaS built on Node.js?
p02,category,Which email sending service do developers recommend in 2026 for a startup?
p03,problem,Our password reset emails keep landing in spam. What service should we switch to?
p04,problem,How can a 3-person team send receipts and alerts by email without managing a mail server?
p05,comparison,Postbird vs Sendly for a startup sending 50k emails a month?
p06,alternatives,What are cheaper alternatives to Postbird for low volume?
c01,control,What is Acme Mail?
```
