# Progress-aware delegation supervisor

ABC v0.2 separates three questions that were previously conflated:

1. **Did the transport deliver the request?**
2. **Is Antigravity still making meaningful progress?**
3. **Is it safe for another agent to write the same workspace?**

## Meaningful progress

A task is active when the observed trajectory changes in a meaningful way, including new trajectory steps, planner-response growth, tool/search/command/file activity, or a new error/status event. A missing final answer by itself is not evidence of a stall.

The watchdog uses idle age since the last meaningful event. The adaptive idle threshold is bounded between 90 and 600 seconds and grows from an EWMA of observed event gaps:

`T_idle = clamp(90s, 600s, 4 * EWMA(gap) + 30s)`

A response slice may yield control back to Codex while work remains active; that returns a nonterminal `ACTIVE_PENDING` snapshot. It does **not** grant a second writer.

## Handoff contract

Transport fallback and agent handoff are different permissions.

- `NOT_SENT` + proven `STALLED`: another writer may take over.
- `PREPARING`, `IN_PROGRESS`, `DELIVERING`, `ACCEPTED_PENDING`, `INPUT_REQUIRED`, or `DELIVERY_UNKNOWN`: read-only review/warm-standby is permitted, but same-workspace writes are fenced because the remote agent may still resume.
- `COMPLETED`: review/follow-up writes are permitted normally.

The v2 receipt exposes:

- `supervisor_state`
- `may_handoff_read`
- `may_handoff_write`
- `remote_may_resume`
- `handoff_reason`

## Rust boundary

`rust/abc-core` contains the deterministic progress/handoff state model. `rust/abc-supervisor` is a dependency-free Rust 1.98.1 line-protocol process. The v2 Python adapter starts at most one supervisor process per wait call and falls back to the equivalent Python watchdog if the 1.98.1 binary is not installed. Mature Antigravity private RPC and delivery-journal transport code remains in the legacy compatibility module until separately ported and regression-proven.

This boundary avoids a risky big-bang rewrite while moving the correctness-critical orchestration decision into a small auditable Rust core.

## Trust boundary

The v2 installer manages a marker-scoped block in `$CODEX_HOME/AGENTS.md`. It records that delegation through **this** locally authenticated ABC/Antigravity entry point is pre-authorized for the user-granted task/workspace. It does not authorize unrelated Gemini services, scope expansion, OS elevation, sandbox bypasses, login prompts, or Antigravity runtime approvals. Local loopback transport also does not imply that model inference itself remains on-device.
