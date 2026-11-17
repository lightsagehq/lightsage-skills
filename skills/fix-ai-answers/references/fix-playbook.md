# From evidence to a fix

## Contents
- Diagnose: five causes and how to tell them apart
- Pattern to fix table
- Owned pages that win prompts
- Influencing third-party sources honestly
- Correcting a wrong claim
- Coding-agent answers
- Ranking
- Verifying

## Diagnose: five causes and how to tell them apart

Work through these in order for each lost prompt cluster. Stop at the first that fits the evidence.

1. **Technical block.** The engine cannot read your page: robots.txt or a CDN bot rule blocks its crawler, the page renders only with JavaScript, it 404s, or it is not indexed. Check: fetch the page, check robots.txt for that engine's bots, search the engine's index for the URL. Hand off to audit-agent-readiness if any fails. No content fix works until this is fixed.
2. **Owned page read but not persuasive.** Your page is cited, yet the answer names a competitor or leaves you out. Check: open the cited page and look for the exact thing the prompt asks (the use case, the comparison, the price, the limit). Usually it is missing, buried, or stated vaguely.
3. **Absent from the sources the engine reads.** The answer cites third-party pages (roundups, review sites, comparison pages, forums) and those pages list competitors, not you. Check: open the top cited pages from the evidence table; note whether you are listed and how competitors are described.
4. **Wrong fact at the source.** The answer states something false about you. Check: search the cited pages and your own old pages, docs and changelog for the false statement.
5. **Answered from memory.** No citations, no search (`web_retrieval_observed` false, or `searched` false in measure-ai-visibility). The answer reflects training data and long-standing consensus. Fixes take months; aim at the sources that shape consensus and at search-enabled runs.

## Pattern to fix table

| Repeated evidence | Likely cause | Fix | Verify with |
|---|---|---|---|
| Your page cited, you not named or not recommended | 2 | Add the missing section to that page: the use case in the prompt's words, a plain comparison, the fact the answer needed | Same prompts; the page stays cited and you get named |
| Competitors named, the same 2–4 third-party pages cited, you not on them | 3 | Get listed on those pages (see below); create an owned page for the intent if none exists | Those URLs list you; then you get named on the prompts that cite them |
| A false claim repeated across runs or engines | 4 | Correct the source; publish the fact with a date on an owned page | Later answers state the right fact and cite the corrected page |
| Named but framed weakly ("also an option", "for enterprises only") | 2 or 3 | State best-fit cases and proof (customers, numbers, dates) on your page, and make third-party profiles say the same | Recommendation and sentiment on comparable reruns |
| One engine loses, others win | its sources differ | Look at what that engine cites; fix there before changing pages for everyone | That engine plus a control engine |
| No citations, competitor named every run | 5 | Long game: docs, package READMEs, registries, reputable roundups, community answers; run search-enabled checks meanwhile | Search-enabled runs first, memory runs over months |
| Coding agent picks a competitor or stalls in your docs | docs and packaging | Fix the quickstart, install command, package name, examples the agent fetched (see below) | Comparable coding-agent runs and their traces |

## Owned pages that win prompts

- One page per buying intent you lose: "<category> for <segment>", "<you> vs <competitor>", "alternatives to <competitor>", a pricing facts page. Check first whether a page already exists that should win; fix it before creating a second one on the same intent.
- Answer the prompt's question in the first lines in plain words, then the proof. State prices, limits, regions and integrations as text with a "last updated" date, not in images or behind a "contact sales" wall.
- Comparison pages should be fair. A self-serving "best X" list on your own site can get cited and still lead answers to recommend competitors; prefer a straightforward "<you> vs <competitor>" with where each fits.
- Make sure the page is linked from your site, in the sitemap, and readable without JavaScript.

## Influencing third-party sources honestly

The evidence table's "sources cited where you lose" with a low "won answers citing" count is your target list.

- **Roundups and "best X" articles:** email the author or editor with a short, factual pitch and what is new or different; offer a trial account. Prioritize pages cited on several lost prompts and engines.
- **Review and comparison sites:** claim and complete your profile with the same category, segment and facts as your own pages; ask real customers for reviews through the site's own process.
- **Forums and communities:** answer real threads where you can help, disclose that you work there, and follow each community's rules. No sock puppets, no bulk posting.
- **Wikipedia and similar:** do not edit your own article; request corrections on the talk page with sources.
- **Docs aggregators, package registries, GitHub lists:** keep your listing current; submit to curated lists through their contribution process.

Never: buy fake reviews, pay for placements presented as independent, or plant posts. They break platform rules and consumer protection law and can be removed, taking your visibility with them.

## Correcting a wrong claim

1. Quote the false statement with run ids and engines; confirm the true fact with the user.
2. Find its origin: the cited pages first, then search the exact phrase or number on the web, then your own older pages, docs, changelog and press releases.
3. Fix your own sources first (update, redirect or add a dated note). Then ask third-party owners to correct theirs, with a link to the dated fact.
4. Publish the correct fact where the engine already looks (the cited owned page, the pricing page) in one plain sentence with a date.
5. Re-check after a recrawl; expect stale answers from memory to lag far behind search-enabled ones.

## Coding-agent answers

Coding agents answer "how do I do X in <stack>" from training data and from the docs they fetch.
- Read `tool_calls` in the run (Lightsage) or `sources_seen` (measure-ai-visibility): which URLs did the agent fetch, and did any 404 or return an empty JavaScript page?
- Typical fixes: a quickstart for the user's stack with a copy-paste install command and a minimal working example; the package README stating what it does in the first line; markdown versions of docs pages on request; consistent package and import names.
- Measure search-enabled and memory runs separately; a docs fix shows up in search-enabled runs first.
- For whether agents pick you while building, hand off to test-agent-pick.

## Ranking

Score each candidate, then keep the top 1–3:
- **Reach:** how many lost prompts and engines it can move, weighted by the revenue value of those prompts.
- **Evidence:** repeated across runs and engines (strong), one engine many runs (medium), one run (weak).
- **Effort:** a section on an owned page (low), a new page or a docs fix (medium), third-party outreach or a product change (high).
- **Speed to show:** owned page already cited (fast), new owned page (medium), third-party and memory answers (slow).

A cheap fix on an owned page that is already cited usually ranks first. Say why each fix ranks where it does.

## Verifying

- Set the check before the change: prompts, engines, runs per prompt (5 or more), the date to re-run, and the success threshold.
- Leading sign: the changed or new page appears in citations, or the third-party page now lists you.
- With about 15 answers on each side, only a move of about 35 points or more is distinguishable from noise; with about 40 per side, about 20 points. Say so when the check is small.
- Keep the original run ids in the check so the before and after are the same prompts on the same engines.
