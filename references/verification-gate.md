# Verification Gate

## Rule

Codex does not trust completion claims without evidence. Worker confidence, a local patch, or a temporary sandbox file is never sufficient by itself.

## Universal checks

- The output matches the requested goal.
- Scope stayed within the user-authorized boundary.
- Constraints were respected.
- Deliverables actually exist.
- The worker did not silently skip a hard requirement.
- If the bridge receipt is non-terminal or ambiguous, do not claim the delegated work is finished.

## Code tasks

Check:

- intended files changed and unrelated files did not;
- implementation matches the requested behavior;
- relevant regression coverage exists;
- local verification was run when feasible;
- no safety boundary was weakened to make the happy path faster.

For Antigravity bridge changes specifically, confirm:

- active trajectory progress does not become a false stall;
- `DELIVERY_UNKNOWN`, `ACCEPTED_PENDING`, `INPUT_REQUIRED`, `PREPARING`, `IN_PROGRESS`, and `DELIVERING` never authorize a second same-workspace writer;
- `safe_to_fallback` and `may_handoff_write` remain separate decisions;
- managed trust remains task/workspace-scoped and preserves user-authored `AGENTS.md` text.

## Remote persistence tasks

When the user asks for a GitHub change, verify the actual remote repository before saying the work is saved:

1. fetch the target branch from GitHub;
2. confirm its HEAD SHA is the expected commit;
3. compare the previous and new SHAs;
4. inspect the remote changed-file list;
5. only then report completion.

A commit that exists only in `/tmp`, a detached worktree, a sandbox, or a local clone is not delivered.

## Writing / documentation tasks

Check:

- language and tone;
- factual consistency with the current implementation;
- commands and paths actually exist;
- documentation does not claim the project is more migrated, local, tested, or automated than it really is;
- obsolete references are removed instead of merely hidden behind newer text.

## Research tasks

Check:

- claims are supported;
- sources are identified when required;
- uncertain points are marked uncertain;
- stale assumptions are not presented as current facts.

## Retry decision

### Accept

Use when the goal and acceptance evidence are both satisfied.

### Re-delegate

Use when the result is salvageable but a bounded gap remains and the original worker is safe to continue.

### Take over directly

Use for a small localized fix when doing so does not violate writer-fencing or delivery safety.

### Escalate

Use when blocked by a real permission/runtime event, missing capability, conflicting requirement, or a delivery state that cannot be reconciled safely.
