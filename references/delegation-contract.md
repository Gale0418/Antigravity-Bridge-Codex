# Delegation Contract

Use one bounded task packet per delegated objective.

## Required fields

### Goal
One concrete outcome.

### Context
Only the files, facts, and workspace area needed for the task.

### Constraints
Examples:
- preserve existing behavior;
- no unrelated refactors;
- use Traditional Chinese;
- do not install packages;
- do not run destructive commands.

### Deliverables
Name exact outputs: patch, document, tests, summary, or evidence.

### Acceptance checks
Write checks Codex can verify independently.

### Stop conditions
Return control when:
- a required tool is unavailable;
- a real permission/runtime event blocks progress;
- requirements conflict;
- the task would exceed the authorized scope.

## Reusable task packet

```text
You are the execution worker for this bounded task.

Goal:
<one outcome>

Workspace / relevant files:
<explicit scope>

Constraints:
<rules and forbidden actions>

Deliverables:
<exact outputs>

Acceptance checks:
<what Codex will verify>

Stop conditions:
<when to return control>

Return:
1. what you changed or concluded
2. evidence for the acceptance checks
3. remaining risks or uncertainties
```

## Delivery identity

Create one stable `request_id` before the first bridge send and retain its receipt.

- same request ID + same fingerprint = retry/reconciliation;
- same request ID + different fingerprint = conflict;
- a non-terminal receipt must reconcile the existing cascade/marker instead of creating a replacement send.

For intentional parallel experts, assign separate `lane_id` values under the same `mission_id`.

## Handoff contract

Do not infer another worker may write from timeout, silence, local lane cancellation, or `STALLED` alone.

A same-workspace replacement writer requires the bridge receipt to explicitly state:

```text
may_handoff_write = true
```

Read-only review/warm standby may proceed when:

```text
may_handoff_read = true
```

while write takeover remains fenced.

`DELIVERY_UNKNOWN`, `ACCEPTED_PENDING`, `INPUT_REQUIRED`, `PREPARING`, `IN_PROGRESS`, and `DELIVERING` never authorize a second same-workspace writer.
