# Eval failure taxonomy

Use this reference to keep diagnoses tied to the layer that can actually fix
them. Fields reflect the public v2 contract retrieved 2026-09-08. Confirm the
current response shape before relying on optional fields.

## Evidence hierarchy

Start with the judge outcome, then test it against execution evidence:

| Evidence | What it can establish | What it cannot establish alone |
| --- | --- | --- |
| run `status`, `stage`, `progress`, `error`, and timestamps | Whether the job reached a terminal state and where a run-level failure surfaced | The agent output or judge outcome when no result exists |
| `passed`, `score`, `failure_reasons` | The judge's verdict and stated rationale | The true root cause |
| `prompt` and `output` | What was requested and what the agent produced | Whether the environment allowed a fair attempt |
| `exit_code`, stdout, stderr | Process success, errors, warnings, and missing prerequisites | Product correctness when execution never reached the product |
| `tool_calls` | Which operations were attempted and with what visible arguments | Hidden state, provider internals, or omitted calls |
| `latency_ms` | End-to-end duration for the result | Which component caused the delay without supporting traces |

Null fields mean the evidence is unavailable. Do not reinterpret them as a
pass, a failure, zero latency, or no tool usage.

## Classification guide

### Product or API behavior

Use when the requested, documented behavior was reached and returned an
incorrect response, inconsistent state, wrong side effect, or reproducible
server failure. Prefer a minimal reproduction and record the affected endpoint
or resource.

### Documentation or discoverability

Use when the product supports the outcome but current public guidance is wrong,
missing, ambiguous, or difficult for the agent to find. Confirm the behavior
against the installed interface before recommending a docs change.

### Agent Skill instructions

Use when the agent had working tools and sufficient information but the loaded
skill routed it incorrectly, omitted a non-obvious invariant, or caused
unnecessary work. Do not patch a skill to mask a product, docs, or fixture bug.

### CLI or MCP integration

Use when the interface parses, serializes, names, or returns something
incorrectly even though the underlying product contract supports the task.
Separate unsupported operations from broken supported operations.

### Eval prompt or judge design

Use when the prompt is underspecified, contradictory, leaks the desired answer,
requires unavailable context, or the judge penalizes a valid outcome. A result
can reveal an eval-design problem without revealing a product problem.

### Configuration or environment

Use for missing repositories, credentials, dependencies, environment values,
supporting skills, CLIs, or MCP servers. Verify that the selected configuration
is known before attributing a difference to it.

### Infrastructure or provider execution

Use for dispatch failures, timeouts, network outages, unavailable models,
container startup failures, or other conditions that prevented a fair attempt.
Report these separately from pass rate unless the eval is explicitly testing
reliability of that layer.

### Insufficient evidence

Use when the result lacks the output or diagnostics needed to choose among
plausible causes. Recommend the smallest additional observation rather than a
speculative fix.

## Cluster before acting

Group results by a concrete signature such as the same command error, missing
resource, judge criterion, wrong API response, or tool-selection pattern. Do
not cluster only because results share a low score.

Prioritize a cluster when it is recurrent, blocks later steps, affects several
agents or configurations, or has high customer impact. A single severe product
or safety defect can outrank a frequent cosmetic failure.

## Validation choices

- Rerun the same eval and configuration after an operational or product fix.
- Compare baseline and candidate configurations when testing a skill, CLI, or
  MCP change; hold agent, repository, environment, docs, and prompt constant.
- Add or repair an eval case when the judge or prompt was the problem, then
  rerun both the baseline and candidate.
- Reproduce outside the eval only when doing so isolates the suspected layer.

Name the expected observable change before rerunning. Do not use reruns merely
to fish for a passing sample, and report retries consistently across compared
conditions.
