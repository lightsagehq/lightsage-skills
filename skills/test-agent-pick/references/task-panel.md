# Writing the task panel

Read when writing or reviewing `tasks.json`.

## The file

```json
{
  "category": "transactional email API",
  "brand": {"name": "YourBrand", "domains": ["yourbrand.com"], "packages": ["yourbrand"], "aliases": ["YourBrand Mail"]},
  "competitors": [{"name": "Competitor A", "domains": ["competitor-a.com"], "packages": ["competitor-a", "@competitor-a/node"]}],
  "tasks": [
    {"id": "ask-01", "kind": "ask", "prompt": "..."},
    {"id": "build-01", "kind": "build", "prompt": "...", "repo": "fixtures/nextjs-app"}
  ]
}
```

- `packages` and `domains` drive the automatic pick guess from code and installs. List every SDK
  name per language (`yourbrand`, `@yourbrand/node`, `yourbrand-python`), and docs hosts that differ from
  the main domain (`docs.x.dev`, `github.com/org/repo`).
- `repo` is a folder, relative to the task file, copied fresh into every run. Omit it for ask
  tasks; the agent then starts in an empty folder.
- Ids are stable labels; never reuse an id for a reworded task, or before/after comparisons break.

## How many and which kinds

- 15 to 30 tasks. Fewer cannot separate stacks; more costs hours for little extra precision.
- About 40% **ask** tasks: the question a developer types before choosing.
  - Open: "What should I use to send transactional email from a Rails app?"
  - Forced: "Pick one email API for this and say why." Forced questions measure the default; open
    ones measure the shortlist. Use both, and label which is which in the id (`ask-open-03`).
- About 60% **build** tasks: the instruction a developer gives in a repo. These show what the
  agent actually installs.
  - "Add a password reset email to this app."
  - "Send a welcome email when a user signs up."
- Spread across the 2 to 4 stacks buyers use (Next.js, FastAPI, Rails, Go, a cron worker). A
  brand usually wins one stack and loses the rest; the panel has to be able to show that.
- Cover the jobs inside the category, not just the headline one (for email: transactional,
  inbound parsing, templates, bulk sends, local testing).

## Phrasing

| Good | Bad (why) |
|---|---|
| "Add search to the docs site in this repo." | "Add Algolia-style instant search." (names a vendor's style) |
| "Which vector database should I use for 2M embeddings on a small budget?" | "What's the best vector DB like Pinecone?" (anchors on one brand) |
| "Store user uploads for this app." | "Store uploads with signed URLs and an image CDN." (only if that is a real buyer need; otherwise it selects for one vendor) |
| "Set up error tracking for this FastAPI service." | "Set up error tracking. We like open source." (persona steers the pick; use only as a labelled variant) |

- Write the way developers type: short, lower effort, no marketing words ("robust", "scalable").
- No brand names, product names, or terms only one vendor uses.
- No "migrate from X to ..." tasks: they name a competitor. Test migration separately if needed.
- One job per task. "Add auth, payments and email" produces three picks and an unreadable result.
- Constraints that real buyers state are fine (budget, region, compliance, self-hosted), but put
  each in its own labelled variant so you can see what it changes.

## Fixture repos

- One per stack, the smallest thing that runs: `package.json` with the framework and nothing else,
  one route or page, a README of one line. Generate with the framework's own starter, then delete
  anything vendor-specific.
- Check before running: `grep -rniE "brand|competitor-a|competitor-b" fixtures/` returns nothing.
  Also check `.env.example`, lockfiles and template READMEs.
- No `node_modules` or virtualenvs (the runner skips them anyway); agents install what they pick.
- Keep fixtures fixed across reruns. Changing a fixture changes the experiment.

## Example panel (email API, 20 tasks)

- ask-open-01..04: Next.js, Rails, FastAPI, Go: "what should I use to send emails from ..."
- ask-forced-01..04: same stacks, "pick one email provider and say why"
- build-01..08: password reset, welcome email, magic-link login, receipt email, across the four fixtures
- build-09..12: inbound email to a webhook, email templates, local email testing, bulk newsletter send

Show the user the panel as a short table (id, kind, stack, prompt) and ask what a real buyer would
never say. Their edits are worth more than another round of your own wording.
