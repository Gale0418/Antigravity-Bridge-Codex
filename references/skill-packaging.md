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
- `skills/`: Contains the plugin skill wrapper. The wrapper delegates to `../../SKILL.md` so the canonical long workflow stays in one place.
- `tests/`: Contains test logic (if applicable).
- `SKILL.md`: The core metadata and prompt instructions for the skill. Must remain ASCII-safe to prevent cp950 errors on Windows systems.

## Installation

Use one of these installers to do both of these:

- copy the skill package to the global `~/.codex/skills/antigravity-bridge-codex` folder
- sync a local plugin marketplace package under `~/.codex/local-marketplaces/antigravity-bridge-codex`, then register or refresh the plugin so the Codex UI can use the packaged icon metadata
- register a stable user-level MCP server named `antigravity_bridge_codex` that points at the marketplace package, so new Codex threads can expose bridge tools through the normal `[mcp_servers]` path even if plugin-provided MCP tools are not mounted

- macOS or any environment without PowerShell 7: run `python3 scripts/install.py`
- Windows or PowerShell 7 environments: run `pwsh scripts/install.ps1`

Re-running either installer updates both the personal skill copy and the local plugin package from this repository. The local plugin package includes both the standard `skills/` wrapper and the root canonical skill resources on Windows and macOS.

## Tool Packaging

The plugin manifest must keep `mcpServers` pointed at `./.mcp.json` and declare `bundledContentVariant` as `legacy-mcp`, matching Codex-bundled MCP plugins so the app treats the package as tool-capable instead of skill-only. Installers must copy both `.mcp.json` and `mcp/` into the plugin root. The personal skill copy also receives those files so a future tool loader or manual recovery command can use the same package contents.

Source `.mcp.json` stays portable with `python3`, and installers skip Windows Store Python aliases while normalizing installed copies to an absolute Python command when possible. This avoids GUI-launched Codex threads failing to spawn the stdio server because their PATH differs from an interactive terminal.

Plugin-provided MCP servers may appear in `codex mcp list` before a Codex app thread exposes them as callable tools. The installer therefore also registers the stable `antigravity_bridge_codex` MCP server with `codex mcp add`, using an absolute server script path under the local marketplace package rather than the versioned plugin cache. This keeps the direct tool route independent of plugin cachebuster versions.

The MCP server intentionally shells no external dependency; it imports `scripts/antigravity_bridge.py` and uses the local Antigravity logs plus localhost RPC. Keep default outputs compact and require an explicit trajectory request for raw debug payloads.
