# Workflow

## Goal

Use a local Antigravity or Gemini CLI as the execution engine while Codex remains responsible for decomposition, review, and final user communication.

## Flow

1. Read the user request and classify the task.
2. Decide whether delegation is worth the packaging cost.
3. Detect the available local executor with a safe, read-only probe.
4. Build a compact task packet.
5. Run the worker.
6. Inspect outputs, artifacts, diffs, or logs.
7. Accept, retry, or take over directly.
8. Reply to the user only after review.

## Task Classification

### Good Delegation Targets

- Drafting long-form content
- Generating boilerplate or repetitive edits
- Implementing a bounded code task with clear acceptance checks
- Writing tests around a known behavior
- Refactoring a narrow file set

### Poor Delegation Targets

- Tasks with unclear goals
- Changes touching security-sensitive logic without precise guardrails
- Broad product design with unresolved trade-offs
- Actions that need local approvals the worker cannot safely choose

## Probe Strategy

Probe the machine in a way that does not mutate state.

Suggested pattern:

1. Check whether each likely command exists.
2. Ask for version or help output.
3. Prefer the most specific Antigravity command if present.
4. Fall back to Gemini CLI only if Antigravity is unavailable.

Record which command was chosen so later retries stay consistent.

## Prompting Strategy

Use short, explicit packets. The worker should not infer hidden goals.

Good packet qualities:

- One concrete objective
- Small file list
- Named deliverables
- Clear acceptance checks
- Explicit stop conditions

Bad packet qualities:

- "Improve this"
- "Fix whatever seems wrong"
- Full-repo dumps without a target
- Hidden expectations not written down

## Review Loop

After each worker run:

1. Check whether the deliverables actually exist.
2. Compare results against the acceptance checks.
3. Decide whether the remaining gaps are:
   - tiny enough to fix directly
   - clear enough to re-delegate
   - risky enough to stop and ask the user

## Final Response Rule

Do not say the task is done because the worker claimed it is done.

Only report completion after Codex has:

- inspected the output,
- verified the required checks,
- and confirmed the result is suitable for the user.
