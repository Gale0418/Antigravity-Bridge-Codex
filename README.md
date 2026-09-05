# Antigravity Bridge Codex

![Version](https://img.shields.io/badge/version-0.2.1-20B2AA) ![Rust](https://img.shields.io/badge/Rust-1.98.1-DEA584) ![License](https://img.shields.io/badge/license-MIT-blue)

**Progress-aware local collaboration between Codex and the user's authenticated Antigravity / Gemini session.**

[繁體中文](README.zh-TW.md)

## What changed in 0.2.x

The bridge no longer treats “no final answer yet” as proof that Gemini is stalled. Long searches, tool calls, file work, and incremental planner output count as meaningful progress. The bridge also exposes explicit handoff-safety facts so Codex does not launch Luna or another writer into the same workspace while the original Antigravity task may still resume.

The installer also manages a narrow trust capsule in `$CODEX_HOME/AGENTS.md`: delegation through this bridge is pre-authorized for the user's current task/workspace scope, so Codex should not repeatedly ask for conceptual permission merely because the collaborator is Gemini or Antigravity. Real runtime permission events still remain real permission events.

## Architecture truth

This repository is **hybrid**, not a completed pure-Rust rewrite.

```text
Codex / MCP
    │
    ├─ progress-aware orchestration ──> scripts/antigravity_bridge_v2.py
    │                                      │
    │                                      ├─ Rust 1.98.1 abc-supervisor
    │                                      └─ handoff / watchdog policy
    │
    └─ compatibility transport ───────> scripts/antigravity_bridge.py
                                           │
                                           ├─ localhost Antigravity RPC
                                           ├─ delivery journal / idempotency
                                           ├─ session discovery
                                           └─ agy fallback
```

The Rust layer owns the new progress-state model and watchdog logic. The mature Python transport remains intentionally retained for private loopback RPC, request journaling, session discovery, and proven delivery semantics until those pieces can be ported independently without weakening safety guarantees.

## Core guarantees

- **Progress-aware waiting.** Search/tool/trajectory activity refreshes the idle watchdog.
- **No false failover from silence alone.** A missing final response is not enough to declare Gemini dead.
- **At-most-once behavior is preserved.** Ambiguous delivery never authorizes a resend through another transport.
- **Second-writer fencing.** `DELIVERY_UNKNOWN`, `ACCEPTED_PENDING`, `INPUT_REQUIRED`, `PREPARING`, `IN_PROGRESS`, and `DELIVERING` do not permit a second same-workspace writer.
- **Bounded handoff facts.** Receipts expose `supervisor_state`, `may_handoff_read`, `may_handoff_write`, and `remote_may_resume`.
- **Scoped trust.** The managed trust capsule covers only this bridge and the current user-granted task/workspace scope.
- **Runtime permissions stay separate.** Login expiry, OS/sandbox restrictions, Antigravity UI approval, elevation, and scope expansion are never bypassed.
- **No false “fully local” claim.** The bridge transport is localhost; configured model inference may still be provided by an external model service.

## State model

| State | Meaning | Same-workspace writer takeover |
| --- | --- | --- |
| `ACTIVE` | Meaningful progress observed | No |
| `QUIET` | No new event yet, still within idle budget | No |
| `SUSPECT` | Quiet long enough to warrant attention | No |
| `ACTIVE_PENDING` | Response slice ended, but work is still alive | No |
| `INPUT_REQUIRED` | Real runtime/login/UI permission event | No |
| `DELIVERY_UNKNOWN` | Request may already have been accepted | No |
| `STALLED` | No meaningful progress beyond the adaptive idle threshold | Only when receipt also proves write handoff safe |
| `DONE` | Completion marker observed | Review/follow-up only |

`may_handoff_read` can be true while write takeover is forbidden, allowing a read-only Luna warm standby or review without creating competing edits.

## Installation

### macOS / Linux

```bash
python3 scripts/install_v2.py
```

### Windows / PowerShell 7

```powershell
pwsh -NoLogo -NoProfile -File .\scripts\install-v2.ps1
```

The installer:

1. runs the proven compatibility installer;
2. copies the Rust workspace into installed skill/plugin trees;
3. builds `abc-supervisor` with **Rust/Cargo 1.98.1** when that exact toolchain is available;
4. installs the binary under the package `bin/` directory;
5. updates the marker-scoped `$CODEX_HOME/AGENTS.md` trust capsule without overwriting user-authored text.

If Rust 1.98.1 is unavailable, installation remains usable through the Python compatibility watchdog and reports that the native supervisor is inactive instead of pretending a Rust build succeeded.

## Primary usage

Use the v2 front door for normal work:

```bash
python3 scripts/antigravity_bridge_v2.py prompt \
  --prompt "Inspect the current workspace and summarize the relevant files." \
  --workspace-path .
```

Smoke check:

```bash
python3 scripts/antigravity_bridge_v2.py smoke --workspace-path .
```

The installed MCP route is declared in `.mcp.json` and loads:

```text
mcp/antigravity_bridge_server_v2.py
```

The older Python/PowerShell scripts are compatibility and diagnostic surfaces, not the preferred orchestration entry point.

## Delegation model

Default role split:

- **Gemini / Antigravity:** creative scout, primary heavy writer/executor, broad first pass.
- **Codex:** planner, scope controller, reviewer, acceptance gate.
- **Luna or another worker:** bounded finisher/reviewer; same-workspace write takeover only when the bridge explicitly marks it safe.

A strong worker answer is still not completion evidence. Codex must inspect the resulting files, receipts, or test output before claiming the task is done.

## Permission boundary

The trust capsule means:

> “Codex may delegate the current user-authorized task/workspace through this locally authenticated Antigravity bridge without asking again merely because the collaborator is Gemini.”

It does **not** mean:

- all Gemini services are globally trusted;
- the bridge can read unrelated files;
- model inference is guaranteed to remain on-device;
- OS, sandbox, login, elevation, or Antigravity UI permissions can be skipped.

## Verification

Python regression checks for the 0.2.x orchestration layer:

```bash
python3 -m unittest tests/test_progress_watchdog.py tests/test_install_v2.py
```

Rust checks, when Rust 1.98.1 is installed:

```bash
cargo +1.98.1 fmt --manifest-path rust/Cargo.toml --all -- --check
cargo +1.98.1 check --manifest-path rust/Cargo.toml --workspace --all-targets --locked
cargo +1.98.1 test --manifest-path rust/Cargo.toml --workspace --all-targets --locked
```

The project does not rely on GitHub Actions as its acceptance gate; local verification and explicit remote commit verification are the source of truth for maintenance work.

## Repository map

```text
.
├── SKILL.md                         # Canonical Codex operating contract
├── agents/openai.yaml              # Invocation/orchestration guidance
├── mcp/
│   ├── antigravity_bridge_server_v2.py  # Primary MCP adapter
│   └── antigravity_bridge_server.py     # Compatibility MCP framing
├── scripts/
│   ├── antigravity_bridge_v2.py     # Primary progress-aware CLI
│   ├── antigravity_bridge.py        # Mature compatibility transport/journal
│   ├── install_v2.py                # Primary installer
│   └── install.py                   # Compatibility installer
├── rust/
│   ├── abc-core/
│   ├── abc-supervisor/
│   └── rust-toolchain.toml          # Rust 1.98.1
└── references/
    ├── progress-aware-supervisor.md
    ├── delegation-contract.md
    ├── collaboration-playbook.md
    ├── known-gotchas.md
    ├── streaming-event-protocol.md
    ├── verification-gate.md
    └── skill-packaging.md
```

## Maintainer rule

Do not weaken `safe_to_fallback = false` or same-workspace writer fencing merely to make failover faster. Transport fallback (`RPC → agy`) and agent handoff (`Gemini → Luna`) are separate decisions with separate safety requirements.

## License

MIT
