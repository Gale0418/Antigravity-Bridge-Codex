# Skill Packaging

This repository serves as the distributable source for the `antigravity-bridge-codex` Codex skill, presented to users as `Antigravity Bridge Codex`.

## Directory Structure

- `.codex-plugin/`: Contains the plugin manifest used when this repository is packaged as a local Codex plugin with its own icon and metadata.
- `.mcp.json`: Advertises the local MCP stdio server when the plugin is loaded with tool support. Keep the server entry explicit with `type: "stdio"`.
- `agents/`: Contains `openai.yaml` which defines the UI integration (display name, short description, icon paths, and invocation policies).
- `assets/`: Contains the SVG icons used by the UI (`icon-small.svg`, `logo-large.svg`).
- `mcp/`: Contains the minimal Python MCP server that wraps the bridge fallback.
- `references/`: Contains playbook documentation and gotchas for the agent to read when invoked.
- `scripts/`: Contains the core PowerShell scripts and the standard-library Python fallback used to communicate with the local Antigravity server.
- `tests/`: Contains test logic (if applicable).
- `SKILL.md`: The core metadata and prompt instructions for the skill. Must remain ASCII-safe to prevent cp950 errors on Windows systems.

## Installation

Use one of these installers to do both of these:

- copy the skill package to the global `~/.codex/skills/antigravity-bridge-codex` folder
- sync a local plugin marketplace package under `~/.codex/local-marketplaces/antigravity-bridge-codex`, then register or refresh the plugin so the Codex UI can use the packaged icon metadata

- macOS or any environment without PowerShell 7: run `python3 _tmp_install_antigravity_skill.py`
- Windows or PowerShell 7 environments: run `_tmp_install_antigravity_skill.ps1`

Re-running either installer updates both the personal skill copy and the local plugin package from this repository.

## Tool Packaging

The plugin manifest must keep `mcpServers` pointed at `./.mcp.json` and declare `bundledContentVariant` as `legacy-mcp`, matching Codex-bundled MCP plugins so the app treats the package as tool-capable instead of skill-only. Installers must copy both `.mcp.json` and `mcp/` into the plugin root. The personal skill copy also receives those files so a future tool loader or manual recovery command can use the same package contents.

Source `.mcp.json` stays portable with `python3`, but installers normalize installed copies to an absolute Python command when possible. This avoids GUI-launched Codex threads failing to spawn the stdio server because their PATH differs from an interactive terminal.

The MCP server intentionally shells no external dependency; it imports `scripts/antigravity_bridge.py` and uses the local Antigravity logs plus localhost RPC. Keep default outputs compact and require an explicit trajectory request for raw debug payloads.
