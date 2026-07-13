# Antigravity Bridge Codex

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![AI Integration](https://img.shields.io/badge/AI-Codex%20%2B%20Gemini-orange.svg)]()

**Antigravity Bridge Codex** is an open-source bridge skill and plugin enabling seamless multi-agent collaboration between **Codex** (GPT-based CLI/IDE assistant) and a locally running **Antigravity** (Gemini-powered desktop application) session.

With this bridge, Codex acts as a supervisor and reviewer while delegating execution, file modifications, research, and creative brainstorming to the local Antigravity Gemini model.

---

## Key Features

- **Automated Session Discovery**: Automatically detects running Antigravity instances and extracts port numbers and CSRF tokens from local system log files across Windows, macOS, and Linux/WSL.
- **Bi-Directional AI Collaboration**: Allows Codex to spawn cascades, send prompts, inspect trajectories, and receive structured responses from local Gemini.
- **Multi-Platform Support**: Works natively on PowerShell 7+ and Python 3.8+ on Windows, macOS, and Linux.
- **Model Auto-Fallback**: Intelligent fallback system matching active Antigravity model identifiers and internal enum placeholders (`MODEL_PLACEHOLDER_M*`).
- **MCP Server Packaging**: Exposes bridge tools directly as a Model Context Protocol (MCP) server for compatible hosts.
- **Privacy & Least Privilege**: Works entirely over local loopback (`127.0.0.1`), respecting local workspace directory permissions.

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
             │     Invoke RPC via Loopback     │
             └──────────────► ◄────────────────┘
                         (127.0.0.1)
```

---

## Quick Start & Installation

### Option 1: PowerShell (Windows / macOS / Linux)

Run the automated installation script:

```powershell
pwsh -ExecutionPolicy Bypass -File ./scripts/install.ps1
```

Or manually discover a running session and send a message:

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
python3 scripts/antigravity_bridge.py send --prompt "Analyze main.py for bugs" --workspace-path "."
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
