# Skill Packaging

This repository is the distributable source for `antigravity-bridge-codex`.

## Current architecture

Packaging must reflect the real hybrid architecture:

- `scripts/antigravity_bridge_v2.py` is the primary progress-aware orchestration front door.
- `rust/abc-core` and `rust/abc-supervisor` contain the Rust 1.98.1 supervisor/policy layer.
- `scripts/antigravity_bridge.py` remains the mature compatibility transport and delivery journal.
- `mcp/antigravity_bridge_server_v2.py` is the primary MCP adapter and deliberately reuses the mature MCP framing implementation.
- `scripts/install_v2.py` and `scripts/install-v2.ps1` are the preferred installers.

Do not describe the package as fully Rust until localhost RPC, session discovery, journal/idempotency, agy fallback, and MCP framing no longer depend on the compatibility Python layer.

## Directory contract

- `.codex-plugin/` — plugin metadata.
- `.mcp.json` — primary MCP stdio declaration; currently points to `mcp/antigravity_bridge_server_v2.py`.
- `agents/` — Codex invocation/orchestration guidance.
- `assets/` — plugin icons/logos.
- `mcp/` — primary v2 adapter plus compatibility framing server.
- `references/` — maintained operational references only; temporary review logs and obsolete design drafts do not belong here.
- `rust/` — Rust 1.98.1 workspace and lockfile.
- `scripts/` — v2 front door/installers plus compatibility transport/diagnostics.
- `skills/antigravity-bridge-codex/SKILL.md` — plugin wrapper delegating to the canonical root `SKILL.md`.
- `tests/` — regression coverage, including progress watchdog and installer trust-capsule tests.
- `SKILL.md` — canonical operating contract.

## Installation

Preferred installers:

### macOS / Linux

```bash
python3 scripts/install_v2.py
```

### Windows / PowerShell 7

```powershell
pwsh -NoLogo -NoProfile -File .\scripts\install-v2.ps1
```

The v2 installer runs the proven compatibility installer first, then layers the v2 additions.

Required behavior:

1. validate the managed trust capsule before mutating installed state;
2. if Cargo/Rust 1.98.1 is available, build `abc-supervisor` **before** mutating installed plugin trees;
3. copy the Rust workspace without `target/`;
4. install the native supervisor under `bin/` when a verified build exists;
5. retain a functional Python compatibility watchdog when Rust 1.98.1 is unavailable;
6. install/update the marker-scoped `$CODEX_HOME/AGENTS.md` trust capsule without overwriting user-authored text;
7. refresh the local plugin registration only after package synchronization succeeds.

The trust block must stay bounded to this bridge and the current user-granted task/workspace. It must not claim that model inference is necessarily local and must not bypass real runtime/OS/sandbox/UI/login/elevation permissions.

## MCP packaging

`.mcp.json` must point to the v2 adapter:

```text
mcp/antigravity_bridge_server_v2.py
```

The v2 adapter intentionally preloads the progress-aware bridge and then reuses the compatibility MCP framing code. Removing the compatibility MCP server before the adapter is rewritten would break the primary MCP route.

The compatibility installer continues to normalize the installed MCP Python interpreter and stable absolute script path because GUI-launched Codex environments may have a different PATH than interactive shells.

## Rust contract

`rust/rust-toolchain.toml` pins:

```toml
[toolchain]
channel = "1.98.1"
profile = "minimal"
components = []
```

Maintenance checks should use the pinned toolchain explicitly and `--locked` where applicable. Build artifacts under `rust/target/` and installed binaries under a source-tree `bin/` are local outputs and must not be committed.

## Compatibility layer retention rule

The following files are intentionally retained even though they are not the preferred user-facing entry points:

- `scripts/antigravity_bridge.py`
- `mcp/antigravity_bridge_server.py`
- `scripts/install.py`
- PowerShell RPC/capability diagnostics used by the mature transport surface

They may be removed only after all of their runtime responsibilities are independently ported and regression-tested. “Old filename” is not sufficient evidence that a file is obsolete.

## Documentation hygiene

Keep repository documentation limited to current operational truth:

- README / README.zh-TW
- SKILL.md
- delegation/collaboration guidance
- progress supervisor design
- known gotchas
- streaming protocol
- verification gate
- this packaging contract

Historical implementation plans, temporary reviewer reports, redundant examples, and design-only visual identity notes should live in Git history rather than the active package tree.
