# Reading results honestly

## Contents
- The three numbers
- Labelling rules
- How sure is a rate
- Comparing two periods or two engines
- What not to claim

## The three numbers

| Number | Counts an answer when | Comes from |
|---|---|---|
| Named (mention rate) | the brand or one of its aliases or domains appears in the answer text | `tally.py extract`, deterministic |
| Recommended | a reader judges the answer tells the buyer to pick or shortlist you | `labels.jsonl`, read by hand |
| Cited (own site cited) | a citation URL is on one of your domains | `tally.py extract`, deterministic |

They move independently. Being cited but not named means the engine read your page and still did not put you on the shortlist; being named but not cited means the engine knows you from elsewhere (training data or third-party pages). Report all three.

"Named first" is only the order among the brands in `brands.json`, ignoring brands the prompt itself names. It is a cheap proxy for position, not a recommendation.

Also report per engine the share of prompts where you were named in at least one run and in most runs. The prompt-level number tells a marketer how many buyer questions they are absent from.

## Labelling rules

Read the full answer in `extracted.jsonl`, not only the quote in `labels.jsonl`.

- `recommended: true` when the answer puts you in its pick, its shortlist, or "best for" a stated case. A list of options with no ranking counts as true if you are presented as a fit for the buyer's stated need.
- `recommended: false` when you are named only as a contrast, a warning, an "also exists", or "not for this use case".
- `sentiment`: `positive`, `neutral`, `negative` or `mixed`, from how the answer describes you, not from whether you won.
- `wrong_claim`: a short statement of what is wrong and what is true ("free tier is 5,000 emails a month, not 3,000"). Only fill it when you can confirm the fact from the user's own pages or from the user. Otherwise leave null and list it as "to check".

Label every line before reporting a recommendation rate. If the user wants to skip labelling, report "named" and "cited" only.

## How sure is a rate

Each rate in the report has a 95% range. For rates over answers, the range resamples whole prompts, because runs of one prompt tend to agree. For rates over prompts, it is a Wilson interval. Under 5 prompts the report gives no range: say the sample is too small for a rate.

Rough width of the range at a rate near 50%:

| Answers (n) | ± about |
|---|---|
| 15 | 25 points |
| 30 | 18 points |
| 60 | 13 points |
| 100 | 10 points |
| 200 | 7 points |

The prompt-level range is wider still, because n is the number of prompts. With 20 prompts, "named on 8/20 prompts" is anywhere from about 20% to 60%.

## Comparing two periods or two engines

- Compare only the same prompts, engines, models, country and runs per prompt. Recompute on the shared prompts if the set changed.
- With about 40 answers on each side, a difference under about 20 points is within noise. With about 100 per side, under about 14 points. Say "no detectable change" rather than "dropped 8 points".
- A single prompt moving from 0/3 to 2/3 runs is a lead to watch, not a result.
- Different engines are different measurements; a gap between them is real only if the ranges do not overlap.
- Read the "unstable prompts" list: they swing between runs and are the first place a content change shows up, and the first place noise shows up.

## What not to claim

- Not "ChatGPT says" from API runs; say "the OpenAI API with web search, model X".
- Not a share of the market or of traffic. These are answers to your prompt set only.
- Not causation from citations. A cited page shows what was read, not why the answer named someone.
- Not a trend from runs on different models or prompt sets.
- State plainly what you could not run (engines without keys, apps not pasted) and that answers vary by run, date, location, login state and model.
