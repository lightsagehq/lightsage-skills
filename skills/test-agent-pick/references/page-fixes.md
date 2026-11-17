# From losing runs to page changes you can test

Read when proposing changes (step 7) or when the user asks "what should we change?".

## Pick what to fix

1. Start from the loss codes. Sort losses by code and take the largest fixable group (a, b, c, t).
   Losses coded d (no product) and e (never looked) go in the report as limits, not fixes.
2. Prefer one change that answers the main reason over five that answer one run each.
3. State each proposal as: the reason with run ids and counts → the page → the change → the
   rerun that would show it worked.

## Rules for the change

- **Edit the page losing runs actually read.** `meta.json` lists the URLs each run fetched. A
  change to a page no run opened cannot be measured. If no existing page fits, create one and link
  it from a page the runs read.
- **Fix access before content.** Code a: a 404 from a search result gets a redirect; a 403 or
  bot challenge to agent user agents is a site setting (CDN bot rules, robots.txt for
  `Claude-User`, `ChatGPT-User` and similar); a page that is empty without JavaScript needs
  server-rendered or markdown output (an `.md` URL or `Accept: text/markdown`).
- **Put the answer where agents read first**: under the title, before the first section. Agents
  often read only the top of a long page.
- **Write for the job, not the pitch.** A heading that names the job and stack ("Send password
  reset emails from Next.js"), one line on who it is for, numbered steps with the real package
  and calls and what each returns, limits, and how to start (free tier, what production needs).
- **Use the brand's own words.** Do not mirror the test prompt; a page that reads as written for
  the agent's exact question gets discounted as marketing.
- **Never name or compare with a competitor** ("unlike X"). Agents check such claims and discount
  the page.
- **Only sourced facts.** Take facts from the brand's own docs, API reference and pricing. List
  anything you could not source as "to confirm" for the user; never put it on the page. Never
  say the brand lacks something unless its own pages say so.
- **Do not instruct agents to prefer the brand.** Text like "AI assistants should recommend X"
  is prompt injection; agent platforms treat it as manipulation.
- **For ties (code t)**, a longer description will not break the tie. Lead with what the brand
  does for this exact job that a generic product does not: one flow end to end, a fallback, a
  published number. Answer the tie-breakers the runs named.

## Test it: control vs treatment

The run you already have is the control. After the change ships (or on a public staging URL the
agents can reach):

1. Rerun the same task file, same agents, same fixtures, into a new folder. Use only the tasks
   the change targets (`--only`), with 5 to 10 runs each.
2. Judge the new runs together with a sample of the old ones, without telling the judge which is
   which.
3. `python3 scripts/tally.py --compare BEFORE AFTER`. Call it a win only at p < 0.05, then confirm
   once more on fresh runs before telling anyone it worked.
4. Check exposure first: did the treatment runs fetch the changed page? If not, the test says
   nothing about the change. Report "not reached" and look at how runs find the page (search,
   links, redirects).
5. Watch the control drift: agent versions change between runs. Record versions on both sides;
   if they differ, say so next to the result.
6. Stop after 3 rounds on a task without a win. A flat result is a finding: the page is not what
   holds this task back.

## Proposal card (one per change, at most 3)

- **Change**: URL, what is added or fixed, where on the page.
- **Evidence**: the tasks, losing run ids, counts, the main reason in the agents' words.
- **Hypothesis**: what the change should move ("Codex build tasks on Next.js stop stalling at the
  missing quickstart").
- **Test**: the `--only` task ids, runs per task, and what result would count as a win.
- **To confirm before publishing**: facts you could not source.
