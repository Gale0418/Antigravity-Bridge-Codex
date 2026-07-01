---
name: antigravity-bridge-codex
description: Use when Codex needs to reconnect a locally logged-in Antigravity session, talk to Gemini through the standalone language server, run capability or multi-turn collaboration checks, coordinate a shared workspace task where Codex supervises Gemini, or recover Antigravity Bridge Codex MCP tools from the plugin package.
---

# Antigravity Bridge Codex Plugin Entry

Read `../../SKILL.md` completely before taking task actions. That root skill file is the canonical workflow and keeps the plugin wrapper small so the source package does not duplicate long bridge instructions.

Resolve bundled resources from the plugin root after reading the canonical skill:

- `../../scripts/` for PowerShell and Python bridge commands
- `../../mcp/antigravity_bridge_server.py` for the stdio MCP server
- `../../references/` for gotchas, collaboration, and verification guidance
- `../../.mcp.json` for the packaged MCP server declaration

If the canonical root skill is unavailable, stop and report that the plugin package is incomplete instead of inventing bridge steps.
