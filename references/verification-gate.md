# Verification Gate

## Rule

Codex does not trust completion claims without evidence.

Review the worker output before replying to the user.

## Universal Checks

- The output matches the requested goal.
- Scope stayed within the allowed boundaries.
- Constraints were respected.
- Deliverables actually exist.
- The worker did not silently skip a hard requirement.

## Writing Tasks

Check:

- requested language and tone
- approximate length
- factual consistency
- no obvious filler or repetition
- structure matches the request

If the user asked for 1000 words, verify the result is actually near that target before reporting success.

## Code Tasks

Check:

- only intended files changed
- implementation matches the requested behavior
- tests were added or updated when needed
- local verification was run when feasible
- no accidental refactors leaked in

## Research Tasks

Check:

- claims are supported
- sources are identified when required
- uncertain points are marked as uncertain
- stale assumptions are not presented as facts

## Retry Decision

### Accept

Use when the result meets the goal and remaining issues are trivial.

### Re-delegate

Use when the result is salvageable but one or two gaps remain.

### Take Over Directly

Use when review would take longer than fixing the remaining issue yourself.

### Escalate To User

Use when the task is blocked by missing tools, permissions, or conflicting requirements.
