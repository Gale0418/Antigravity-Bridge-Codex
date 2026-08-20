# Antigravity Bridge Codex

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![AI Integration](https://img.shields.io/badge/AI-Codex%20%2B%20Gemini-orange.svg)]()

**Antigravity Bridge Codex** is an open-source bridge skill and plugin enabling seamless multi-agent collaboration between **Codex** (GPT-based CLI/IDE assistant) and a locally running **Antigravity** (Gemini-powered desktop application) session.

With this bridge, Codex supervises local Antigravity Gemini work. The default auto transport is visible-first: it tries Hub-native private loopback RPC first and may fall back to agy only after a confirmed pre-dispatch failure. Ambiguous or accepted delivery never falls back; explicit rpc and agy modes remain available.

---

## Key Features

- **Automated Session Discovery**: Automatically detects running Antigravity instances and extracts port numbers and CSRF tokens from local system log files across Windows, macOS, and Linux/WSL.
- **Visible-first prompting**: `auto` starts a Hub-native RPC conversation and falls back to official `agy` only after failure; receipts expose transport, visibility, IDs, and continuation semantics.
- **Multi-Platform Support**: Works natively on PowerShell 7+ and Python 3.8+ on Windows, macOS, and Linux.
- **Model Selection**: Uses the official `agy --output-format json models` catalog with explicit/env/catalog/recent/default precedence, lane-aware ranking, and a verified RPC-compatible fallback.
- **Health and Coordination**: Read-only health checks, a conservative circuit breaker, and opt-in SQLite lane leases provide owner/epoch fencing, quotas, cancellation, and safe recovery decisions.
- **MCP Server Packaging**: Exposes bridge tools directly as a Model Context Protocol (MCP) server for compatible hosts.
- **Privacy & Least Privilege**: Keeps the workspace explicit; the primary RPC stays on local loopback, and the fallback reuses the locally authenticated official `agy` client.

---

## Architecture Overview

```
 ┌──────────────────────────────────────────────────────────┐
 │                     User Workspace                       │
 └────────────────────────────┬─────────────────────────────┘
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
   ┌───────────────────┐             ┌───────────────────┐
   │   Codex (GPT)     │             │ Antigravity (App) │
   │ Supervisor/Review │             │ Gemini Executor   │
   └─────────┬─────────┘             └─────────┬─────────┘
             │                                 │
             │  auto: Hub RPC → agy fallback   │
             └──────────────► ◄────────────────┘
                  (authenticated CLI)
```

---

## Quick Start & Installation

### Option 1: PowerShell (Windows / macOS / Linux)

Run the automated installation script:

```powershell
pwsh -ExecutionPolicy Bypass -File ./scripts/install.ps1
```

For low-level diagnostics, manually discover a running session and send a private IDE RPC message:

```powershell
. ./scripts/Discover-AntigravitySession.ps1
$session = Get-AntigravitySessionInfo
$cascade = New-AntigravityCascade -WorkspacePaths @($PWD.ProviderPath) -Session $session
Send-AntigravityMessage -CascadeId $cascade.CascadeId -Text "Hello from Codex!" -Session $session
```

### Option 2: Python (Cross-Platform CLI)

Run the Python installation script:

```bash
python3 scripts/install.py
```

Send a prompt directly via CLI:

```bash
python3 scripts/antigravity_bridge.py prompt --prompt "Analyze main.py for bugs" --workspace-path "." --model "gemini-3.6-flash-high"
```

---

## Repository Structure (Illustrative)

```text
antigravity-bridge-codex/
├── .codex-plugin/           # Codex plugin manifest definitions
├── .mcp.json                # MCP server configuration
├── SKILL.md                 # Agent prompt instructions and workflow rules
├── README.md                # English documentation
├── README.zh-TW.md          # Traditional Chinese documentation
├── agents/                  # Subagent definition files
├── mcp/                     # MCP server runner & tools
├── references/              # Protocol specifications & design notes
├── scripts/
│   ├── Discover-AntigravitySession.ps1  # Session auto-discovery script
│   ├── Invoke-AntigravityBridge.ps1     # High-level bridge invocation
│   ├── Invoke-AntigravityRpc.ps1        # Low-level RPC client
│   ├── Run-AntigravityCapabilityMatrix.ps1 # Capability testing
│   ├── antigravity_bridge.py            # Python bridge CLI & library
│   ├── install.ps1                      # PowerShell installer
│   └── install.py                       # Python installer
├── skills/
│   └── antigravity-bridge-codex/
│       └── SKILL.md         # Plugin skill wrapper to the root SKILL.md
└── tests/
    ├── Test-Discover-AntigravitySession.ps1
    ├── Test-Invoke-AntigravityBridge.ps1
    ├── Test-E2E-Smoke.ps1               # End-to-end integration test
    └── test_antigravity_bridge_py.py
```

---

## Operating Modes

1. **Quick Smoke Check**: Verifies that the local Antigravity language server is reachable.
2. **Capability Matrix**: Tests file reading, writing, web search, and multi-turn memory capabilities.
3. **Collaborative Chat**: Establishes a multi-turn session where Codex delegates tasks to Gemini and reviews output before final acceptance.

---

## Running Integration Tests

To run the full unit and integration test suite:

### PowerShell Pester Tests

```powershell
pwsh -Command "Invoke-Pester -Path ./tests"
```

### Python Pytest Suite

```bash
pytest tests/
```

---

## License

This project is licensed under the [MIT License](LICENSE).
## Conversation visibility and transcripts

The default Hub-native RPC path is indexed by Antigravity and is expected to appear at least under `Outside of Project`; Project classification remains controlled by the desktop app. On Antigravity 2.4.3, the `agy` fallback may be completely invisible because the desktop loader looks for a legacy `.pb` trajectory while the CLI writes SQLite `.db` files. Never inject or convert trajectory files to force visibility.

The PowerShell wrapper and `agy` fallback can append a local Markdown transcript. Set `ANTIGRAVITY_BRIDGE_TRANSCRIPT_DIR` to choose a dedicated Codex-readable folder, or use `-TranscriptDirectory` in PowerShell. Use `-NoTranscript` / `--no-transcript` when local persistence is undesirable.
## Reliable delivery and retry contract

auto is visible-first: it tries Hub-native loopback RPC before agy. The Python bridge treats a prompt as a delivery operation, not a fire-and-forget chat message.

- The caller creates a UUID request_id before the first call, preserves the receipt, and reuses that key for every retry. A missing ID is generated only for one invocation; separately generated IDs cannot deduplicate later calls.
- The persistent SQLite journal defaults to %LOCALAPPDATA%\AntigravityBridge\requests.sqlite3. It stores request fingerprints, delivery state, cascade/marker IDs, and receipts—never prompt text or CSRF tokens.
- The same request_id with different request content returns CONFLICT, not a retry.
- Once SendUserCascadeMessage begins, DELIVERY_UNKNOWN, IN_PROGRESS, and other pending/non-terminal outcomes must reconcile the same key, cascade, and marker. They must not send a new prompt or fall back to agy.
- One global deadline spans RPC, reconciliation, and any eligible agy fallback; after it expires, fallback is skipped.

mission_id and lane_id are deliberate fan-out metadata. Add an owner to opt into durable lane coordination; an active lane requires the exact owner and epoch, while denials never bypass coordination through agy fallback.

    python3 scripts/antigravity_bridge.py lane claim --mission-id review-2026-08-21 --lane-id security --owner-id reviewer-1 --quota 3
    python3 scripts/antigravity_bridge.py prompt --prompt "Review src/main.py" --workspace-path . --request-id "550e8400-e29b-41d4-a716-446655440000" --mission-id review-2026-08-21 --lane-id security --owner-id reviewer-1 --lane-epoch 1
    python3 scripts/antigravity_bridge.py health --no-probe

Set `ANTIGRAVITY_ALLOWED_WORKSPACES` (OS path-separator delimited) to enforce an allow-list. Permission waits are returned as non-terminal `INPUT_REQUIRED`; approve them in Antigravity and reconcile the same request ID. `DELIVERY_UNKNOWN`, `INPUT_REQUIRED`, and unowned processes never authorize restart.

PowerShell is a compatibility/diagnostic layer and has no independent persistent request journal; use Python CLI or MCP for idempotent delivery.

This follows [AWS idempotent API](https://docs.aws.amazon.com/ec2/latest/devguide/ec2-api-idempotency.html) client-token guidance. Long-running MCP operations may report [progress](https://modelcontextprotocol.io/specification/latest/basic/patterns/progress) or receive [cancellation](https://modelcontextprotocol.io/specification/latest/basic/patterns/cancellation); timeout/cancellation is not proof that delivery never occurred.
