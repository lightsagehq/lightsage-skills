# Diagnosis template

Use this shape for a single-run diagnosis. For a recurring review, repeat
sections 2-5 per eval and merge the actions; for a regression, add the
baseline run to section 2 and the version and configuration changes to
section 6.

1. **Headline:** one bold line naming the eval and the cause.
   "**Diagnosis: the Welcome email eval failed because the agents call
   `Emails.send`, which the v9 SDK renamed; the docs quickstart still shows
   it.**"
2. **Which run:** the run ID and when it was created, why it counts as failed
   (the run itself failed, some attempts errored before the judge could score
   them, the judge failed an attempt, or the agent recommended the competitor
   or neither company), and whether the run finished normally. When the
   newest run that ended in failure is a different run, name it with its date
   and eval and offer to look at it instead.
3. **Summary table:** eval name with a short ID; agents with versions;
   attempts scored and whether results were truncated; pass rate with n; each
   judge's score and whether it passed.
4. **What worked:** a short paragraph on what passed, including builds, tests
   and how the agent recovered from errors.
5. **What failed:** a numbered list, one item per failing judge or criterion:
   the check, its verdict, and the concrete evidence (file, command, error
   line, missing behavior), with the result ID it came from.
6. **Root cause:** one paragraph, labeled as seen directly or inferred.
7. **Actions:** at most five unless the user asks for all, ordered by
   expected impact, recurrence, confidence and effort. Title each with what
   to do and its priority, then:
   - **Layer:** from the taxonomy, observed or inferred
   - **Evidence:** only what goes beyond the write-up so far (another run
     with the same cause)
   - **Change:** the concrete artifact or behavior to modify and its likely
     owner
   - **Confidence and effort:** high, medium or low
   - **Verify:** the smallest rerun or comparison and the change it should
     show; note that a rerun uses usage-based credits
8. **Limits:** what the diagnosis rests on and what you did not inspect
   (truncated results, trace pages not read, single attempts).
9. **Next step:** offer the most useful follow-up, such as applying action 1
   and rerunning with 3 runs per prompt.

Lead with pass-rate and score changes only when the runs are a valid
comparison. Keep infrastructure failures apart from evaluated failures.

Write for someone who hasn't read the API. Say "the judge failed the only
attempt", not `passed: false`; say "two attempts errored before they could be
scored", not `progress.failed: 2`. Keep IDs as references, not as the
explanation.
