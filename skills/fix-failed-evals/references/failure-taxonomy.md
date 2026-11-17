# Eval failure taxonomy

Contents
- Evidence hierarchy
- Layers and what fixes them
- Common signatures
- Cluster before acting
- Validation choices

Keep each diagnosis tied to the layer that can actually fix it. Field names
reflect the public v2 eval-run contract as of 2026-11; confirm the current
response shape before relying on an optional field.

## Evidence hierarchy

Start with the judge outcome, then test it against execution evidence.

| Evidence | What it can establish | What it cannot establish alone |
| --- | --- | --- |
| Run status, stage, progress, error, timestamps | Whether the job reached a terminal state and where a run-level failure surfaced | The agent's output or the judge outcome when no result exists |
| Result passed, score, failure reasons | The judge's verdict and stated rationale | The true root cause |
| Grader results and their criteria verdicts (`PASS`, `FAIL`, `NOT_VERIFIED`, `NOT_APPLICABLE`) with evidence | Which criteria each check passed or failed, and what it cited | Whether the judge applied the criterion fairly |
| Grader deductions | Shortcomings on checks that still passed | Whether they matter to the user |
| Setup output (command, exit code, output tail) | Whether the start state was prepared | Anything after the agent started |
| Agent version, web retrieval and search observed | Which agent build ran; whether it fetched docs or worked from memory | Whether the docs it fetched were correct |
| Preference result | Which company an Agent Preference attempt recommended | Why it recommended it |
| Prompt and stored analysis (verdict, outcome, findings, bottleneck) | What was asked and the stored diagnosis of the attempt | Whether the environment allowed a fair attempt |
| Trace tool-call, tool-result and error events | Which operations ran, what they returned, where execution stopped | Hidden state, provider internals, omitted calls |
| Latency and per-tool-call durations | End-to-end and per-call time | Which component caused a delay without the trace |

Null fields mean the evidence is unavailable. Don't read them as a pass, a
failure, zero latency or no tool usage.

## Layers and what fixes them

### Product or API behavior

The documented behavior was reached and returned a wrong response,
inconsistent state, wrong side effect or reproducible server error. Prefer a
minimal reproduction and name the affected endpoint or resource. Fix owner:
product or API team.

### Documentation or discoverability

The product supports the outcome but public guidance is wrong, missing,
ambiguous or hard for an agent to find (404 on a guessed docs URL, an old
method in the quickstart, no example of a required field). Confirm the
behavior against the real interface before recommending a docs change.

### Agent Skill instructions

The agent had working tools and enough information, but the loaded skill
routed it wrong, omitted a non-obvious invariant or caused needless work.
Don't patch a skill to mask a product, docs or fixture bug.

### CLI or MCP integration

The interface parses, serializes, names or returns something wrong although
the product supports the task, or a tool's description and errors steer the
agent wrong. Separate unsupported operations from broken supported ones.

### Eval prompt or judge design

The prompt is underspecified, contradictory, leaks the answer or needs
context the agent can't have; or the judge penalizes a valid outcome, demands
something never asked, or can't see the evidence (`NOT_VERIFIED`). A result
can reveal an eval-design problem without revealing a product problem.

### Configuration or environment

Missing or wrong repository, credentials, dependencies, environment values,
skills, CLIs or MCP servers; a failed setup command; an empty or placeholder
credential. Verify that the configuration is known before attributing a
difference to it.

### Infrastructure or provider execution

Dispatch failures, timeouts, network outages, unavailable models, sandbox
start failures, attempts that errored before a verdict. Report these apart
from pass rate unless the eval is testing that layer's reliability.

### Insufficient evidence

The results lack the output or diagnostics to choose among plausible causes.
Recommend the smallest extra observation (read the trace page around the
error, rerun one attempt with the same configuration) rather than a guess.

## Common signatures

| Seen in the evidence | Likely layer | First check |
| --- | --- | --- |
| Attempts errored before a verdict; run error mentions sandbox, dispatch or timeout | Infrastructure | Same error in other evals that day? |
| Setup command non-zero exit | Configuration | Run the command's own error; package or repo moved? |
| 401/403 in tool results | Configuration (credential) or docs (wrong header) | Is the credential in the environment attached to this run? |
| 404 on a docs URL the agent guessed | Documentation | Does the old path redirect? |
| Method or flag that doesn't exist, often with no web retrieval | Documentation or SDK | Is it the old name? Does the SDK error point to the new one? |
| Agent finished, judge says a criterion wasn't verified | Eval judge design, or the agent never ran its code | Did the agent print or run the result in the trace? |
| Judge fails something the prompt didn't ask | Eval prompt or judge design | Re-read the prompt against the criterion |
| Pass rate dropped with a new agent version or configuration | Agent change or configuration | Baseline comparison; rerun the old configuration if possible |
| MCP tool called with wrong arguments, or a tool error the agent can't act on | CLI or MCP integration | Tool description, schema and error text |
| Agent Preference `lost`/`tie` | Product positioning or docs (not a defect) | How the agent reached its recommendation in the trace |

## Cluster before acting

Group results by a concrete signature: the same command error, missing
resource, criterion, wrong response or tool-selection pattern. Don't cluster
only because results share a low score.

Prioritize a cluster when it recurs, blocks later steps, affects several
agents or configurations, or has high customer impact. A single severe product
or safety defect can outrank a frequent cosmetic one.

## Validation choices

- Rerun the same eval and configuration after an operational or product fix.
- Compare baseline and candidate configurations when testing a skill, CLI,
  MCP or docs change; hold agent, repository, environment and prompt constant.
- Add or repair an eval case when the judge or prompt was the problem, then
  rerun both baseline and candidate.
- Reproduce outside the eval only when that isolates the suspected layer.
- Use 3 or more runs per prompt and agent for any claim about rates.

Name the expected observable change before rerunning. Don't rerun just to
fish for a passing sample, and report retries the same way across compared
conditions. Every rerun uses usage-based credits: ask first.
