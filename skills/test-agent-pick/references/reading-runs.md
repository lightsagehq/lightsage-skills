# Reading runs: judging, loss codes, numbers

Read when judging runs (step 5) and before writing the report.

Contents: judging rubric · loss codes · stalls · numbers and sample sizes · what not to claim

## Judging rubric

Judge from the run folder, never from the automatic guess: `answer.md` (final message),
`diff.txt` (what it changed), `meta.json` (searches, fetched URLs, fetch errors, installs,
denials). One entry per run in `judgments.json`:

- `pick`: the one vendor the run chose as its primary choice.
  - Build task: the vendor whose SDK or API the code uses. Code beats prose: an answer that praises
    the brand but installs a competitor picked the competitor.
  - Ask task: the vendor it recommends as the default. If it recommends a stack, the vendor doing
    the job the task asked about.
  - `"none"` when it picks nothing or says "it depends" with no default. Write the name of an
    unlisted vendor when it picks one; the report lists it.
- `pick_type`:
  - `sole`: the one recommendation, or the stated default.
  - `split`: one of two or three options split by a condition ("Brand if you're on Vercel,
    Competitor A otherwise"). Put the option named first, or called the clearest match, in `pick`.
  - `none`: listed, compared or mentioned without being recommended. Row one of a table is not
    a recommendation.
- `reason`: one line in the agent's words, quoted where possible ("has a first-party Next.js SDK").
- `code`: for every run the brand did not win, one loss code below.
- `stall`: where the run stopped short of a working result, in a few words ("asked for an API key
  and stopped", "404 on quickstart, guessed the import"). Empty if it finished.
- `judged`: `true`.

When the same judge reads before-and-after folders, mix the runs and do not say which folder a
run came from.

## Loss codes

| Code | The run... | What could fix it |
|---|---|---|
| a | could not reach or read the brand's page (403, 404, bot block, JavaScript-only, timeout) | Redirect, server-rendered or markdown docs, bot settings |
| b | read the brand's pages but did not find how to do this job (steps, SDK for this stack, limits) | A page change (see page-fixes.md) |
| c | was put off by something commercial: no visible free tier, pricing, or a sales-only start | Publish the facts, if they are true |
| d | found the brand has no product for this job | Nothing on a page. Report as a product gap |
| t | read the brand, described it accurately, and still called it level with a rival | Lead with what the brand does for this exact job that a generic product does not |
| e | never looked the brand up: it chose from memory or only searched the competitor | Not page-fixable in the short run. Third-party content and time |

Most losses are e on ask tasks. Say so plainly: no docs edit moves a run that never reads the docs.

## Stalls

Count separately from picks; a pick that stalls is a loss the brand can often fix.

- Credentials: stopped at "set YOUR_API_KEY", signup, email verification, a card before first use.
- Docs: 404 or wrong page from a search result, an outdated import, an SDK name that does not exist.
- Tooling: a CLI that prompts interactively, an install that fails, a package with a stale name.
- Harness: permission denials and timeouts. These are the test's limits; never blame the vendor.

## Numbers and sample sizes

- Report k/n and the 95% interval `tally.py` prints. 7 of 24 is 29% with an interval of 15% to 49%:
  wide. Two agents whose intervals overlap heavily are not shown to differ.
- n is runs, not tasks. With 3 runs of 20 tasks, n = 60 per agent; runs of the same task are not
  independent, so also look at the per-task table: a share carried by one task is fragile.
- Detecting a change needs more runs than people expect (one-sided Fisher exact test):
  - 1 of 5 to 4 of 5: p = 0.10, not shown. 0 of 5 to 4 of 5: p = 0.02.
  - 2 of 10 to 6 of 10: p = 0.09, not shown.
  - 12 of 60 to 24 of 60: p = 0.01, shown. 12 of 60 to 21 of 60: p = 0.05, borderline.
  - So: judge a page change on the tasks it targets, with 5 to 10 runs each, not on 3.
- Automatic picks are a starting point. If the report still says picks are unjudged, do not send it.

## What not to claim

- Not "agents prefer X" from one agent, one model or one day. Name the agent, version and date.
- Not "the docs change caused it" without a before-and-after rerun on the same tasks and agents.
- Not why the model "thinks" something. Keep observation (what runs did), pattern (what repeats
  across runs) and hypothesis (why) apart, and label hypotheses.
- Not that local runs match what the user's customers see: their agents have project rules, MCP
  servers and memories that clean runs remove on purpose.
