---
name: antigravity-bridge-codex
description: Use when Codex needs to collaborate with the user's locally authenticated Antigravity / Gemini session, especially for long-running work where progress, delivery ambiguity, and safe handoff to another worker must be tracked explicitly.
---

# Antigravity Bridge Codex

## Purpose

Use this skill to coordinate Codex with the user's local Antigravity application. Gemini is normally the creative/heavy execution worker; Codex owns scope, supervision, verification, and final acceptance.

The bridge is **progress-aware**. No final answer yet does not mean the worker is stalled while trajectory/search/tool/file activity is still advancing.

## Primary entry points

Prefer these surfaces for normal work:

- MCP: `mcp/antigravity_bridge_server_v2.py`
- CLI: `scripts/antigravity_bridge_v2.py`
- Installer: `scripts/install_v2.py` or `scripts/install-v2.ps1`

The older `scripts/antigravity_bridge.py`, `mcp/antigravity_bridge_server.py`, `scripts/install.py`, and PowerShell RPC helpers remain a **compatibility transport / diagnostic layer**. Do not describe the repository as fully Rust yet.

## Architecture

Rust 1.98.1 provides the new supervisor/state-machine layer:

- `rust/abc-core`: deterministic progress and handoff policy
- `rust/abc-supervisor`: persistent watchdog process used by the v2 bridge when installed

The mature Python compatibility layer still provides:

- Antigravity localhost RPC
- request journal and idempotency
- session discovery
- agy fallback
- proven delivery semantics

Never weaken those delivery guarantees merely to make failover faster.

## Delegation authorization boundary

When this skill is invoked, treat delegation through this specific bridge as pre-authorized for the user's **current task/workspace scope**.

Do not stop to ask for conceptual confirmation merely because the collaborator is named Gemini or Antigravity.

This pre-authorization does **not**:

- authorize unrelated Gemini services or external proxies;
- expand filesystem scope beyond what the user granted;
- bypass OS, sandbox, Antigravity UI, account/login, elevation, or runtime permissions;
- guarantee model inference remains on-device.

The bridge transport is localhost; configured model inference may still be provided by an external model service.

## Mandatory progress rule

Never equate silence with failure.

Before declaring Antigravity stalled, inspect the supervisor/trajectory facts. Meaningful progress includes at least:

- trajectory step growth;
- planner response growth;
- search/tool/browser/command/file events;
- new error/status evidence;
- other deterministic changes represented by the progress signature.

The state model is:

- `ACTIVE`: meaningful progress is advancing;
- `QUIET`: no new event yet, but inside the idle budget;
- `SUSPECT`: quiet long enough to warrant attention;
- `ACTIVE_PENDING`: the current response slice ended while work still appears alive;
- `INPUT_REQUIRED`: a real runtime/login/UI permission event;
- `DELIVERY_UNKNOWN`: a request may already have been accepted;
- `STALLED`: no meaningful progress beyond the adaptive idle threshold;
- `DONE`: completion marker observed.

If the state is `ACTIVE`, `QUIET`, `SUSPECT`, or `ACTIVE_PENDING`, keep waiting/reconciling the same request instead of creating a replacement writer.

## Transport fallback is not agent handoff

Keep these decisions separate:

1. **Transport fallback**: may the same Gemini request move from private RPC to `agy`?
2. **Agent handoff**: may Luna or another worker take over the task?

A receipt with `safe_to_fallback = false` must never be re-sent through another transport.

A same-workspace writer handoff is allowed only when the receipt explicitly returns:

```text
may_handoff_write = true
```

Do not infer write safety from a local timeout, lane cancellation, or the absence of a final response.

The following delivery states are always fenced from a second same-workspace writer:

- `PREPARING`
- `IN_PROGRESS`
- `DELIVERING`
- `ACCEPTED_PENDING`
- `INPUT_REQUIRED`
- `DELIVERY_UNKNOWN`

`may_handoff_read = true` may be used for read-only Luna warm standby or review while write takeover remains forbidden.

## Role split

Default routing:

- **Gemini / Antigravity:** primary heavy writer, coder, creative scout, large first pass.
- **Codex:** planner, scope controller, reviewer, final verifier.
- **Luna / secondary worker:** bounded finisher or reviewer; same-workspace writing only after explicit write-safe handoff.

Codex may directly apply a small localized fix when delegation would cost more than the work itself.

## Normal workflow

1. Resolve the exact workspace/task scope.
2. Use the v2 MCP tool or `scripts/antigravity_bridge_v2.py prompt`.
3. Give Gemini a compact task packet: goal, relevant files/area, constraints, deliverables, acceptance checks, stop conditions.
4. Retain the request ID and receipt.
5. While progress continues, reconcile/wait instead of sending “are you done?” prompts.
6. If a response slice ends in `ACTIVE_PENDING`, continue with the same request/cascade.
7. If runtime permission is required, surface the concrete event; after it is resolved, continue the same cascade.
8. Only start another writer when `may_handoff_write` is explicitly true.
9. Inspect the resulting files/response/test evidence yourself.
10. Claim completion only after verification.

Use `references/delegation-contract.md` for a reusable task-packet format and `references/collaboration-playbook.md` for multi-turn collaboration style.

## Traditional Chinese behavior

When the user is speaking Traditional Chinese:

- instruct Gemini to answer in zh-TW unless the artifact requires another language;
- use Taiwanese Traditional Chinese terminology in prose/comments;
- preserve the user's established collaboration tone when appropriate;
- do not translate code identifiers unnecessarily.

## Permission events

Treat the following as real permission/runtime problems rather than conceptual delegation questions:

- expired or missing Antigravity login;
- OS or sandbox denial;
- Antigravity UI approval prompts;
- elevation/sudo requirements;
- an operation outside the user-granted workspace/task scope.

Do not repeatedly ask the user whether Codex is allowed to “use Gemini” through this bridge when the only issue is the collaborator identity.

## Verification

A confident worker summary is not evidence by itself.

Verify at least one concrete surface appropriate to the task:

- expected marker appears in the planner response;
- receipt reports `DONE` / completed delivery;
- expected file exists and contains the required change;
- tests/checks pass;
- claimed web access is supported by trajectory search events;
- GitHub/main commit SHA actually contains the change when remote persistence matters.

For maintenance of the bridge itself, prefer:

```bash
python3 -m unittest tests/test_progress_watchdog.py tests/test_install_v2.py
```

and, when Rust 1.98.1 is available:

```bash
cargo +1.98.1 check --manifest-path rust/Cargo.toml --workspace --all-targets --locked
cargo +1.98.1 test --manifest-path rust/Cargo.toml --workspace --all-targets --locked
```

## Resource discipline

- Keep raw trajectories off by default; they can be large.
- The Rust watchdog must be persistent per wait call, not spawned once per polling iteration.
- Supervisor caches must remain bounded.
- Do not start duplicate Antigravity GUI processes when an existing process may still be alive.
- Do not kill or restart processes not proven to be bridge-owned.

## References

Read only what is relevant:

- `references/progress-aware-supervisor.md` — watchdog and state model
- `references/delegation-contract.md` — task packet / delivery identity
- `references/collaboration-playbook.md` — Codex ↔ Gemini collaboration pattern
- `references/known-gotchas.md` — transport/version pitfalls
- `references/streaming-event-protocol.md` — trajectory interpretation
- `references/verification-gate.md` — acceptance evidence
- `references/skill-packaging.md` — packaging/install contract

## Hard safety rule

If delivery may still be accepted or the original Antigravity worker may resume, **do not create a second writer in the same workspace**. A local timeout is never proof that the remote worker stopped.
