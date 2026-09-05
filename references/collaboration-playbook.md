# Collaboration Playbook

Use this playbook for user + Codex + Antigravity/Gemini collaboration.

## Role split

- **Gemini / Antigravity:** creative scout, primary heavy writer/executor, broad first pass.
- **Codex:** planner, scope controller, reviewer, final acceptance gate.
- **Luna / secondary worker:** bounded finisher or reviewer; same-workspace writing only when the bridge explicitly marks handoff write-safe.

## First turn

For a fresh cascade, identify Codex briefly and state the working relationship once. Do not repeat the introduction every turn.

Example:

```text
Codex here. I will define scope and verify the result; please take the heavy first pass on the Antigravity side. If a requirement or permission event blocks you, report it explicitly instead of guessing.
```

Then move immediately to the task packet.

## File-aware handoff

When local artifacts are involved:

- name exact files when known;
- otherwise name the narrow repository area to inspect;
- if the user authorized whole-workspace inspection, name the workspace root and ask for a summary-first map before file-level edits;
- do not ask Gemini to “fix whatever looks wrong” without boundaries;
- include acceptance checks when precision matters.

## Turn taking

1. Send one bounded objective.
2. Observe Gemini's actual response/trajectory.
3. Follow up from real evidence, not a pre-scripted future conversation.
4. Re-state only the constraints that are at risk of being forgotten.
5. Verify the artifact before accepting the result.

## Long-running work

Do not interpret a slow or missing final reply as failure while meaningful progress continues.

Progress evidence can include:

- trajectory step growth;
- search/tool/browser/command/file events;
- planner-response growth;
- other deterministic supervisor-signature changes.

If the response slice ends in `ACTIVE_PENDING`, keep the same request/cascade and reconcile later. Do not launch a replacement writer just to make the chat feel responsive.

## Read-only warm standby

When `may_handoff_read = true` but `may_handoff_write = false`, Luna or another reviewer may inspect the task, acceptance criteria, or current artifacts read-only.

This can reduce takeover latency without creating competing edits.

If Gemini becomes active again, the standby reviewer should remain non-writing unless a separate independent lane was explicitly assigned.

## Forgetfulness guardrail

Gemini can generate strong ideas and still skip details. Reduce that risk by giving it:

- the goal;
- current file/workspace scope;
- constraints;
- deliverables;
- acceptance checks;
- stop conditions.

Do not spend Codex tokens writing the entire solution first unless the remaining work is already small enough to patch directly.

## Markers

Use a unique completion marker for automation/smoke checks when exact capture matters. Avoid decorative markers in casual human-visible chat.

## Review gate

Before reporting success, Codex must independently check:

- the response actually answered the requested objective;
- expected files/artifacts exist;
- required tests/evidence pass when applicable;
- scope did not drift;
- a GitHub change is actually present on the remote target branch when persistence matters.

A confident summary from any worker is not sufficient completion evidence.
