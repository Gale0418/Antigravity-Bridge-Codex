# Skill Packaging

This repository serves as the distributable source for the `antigravity-gemini-bridge` Codex skill.

## Directory Structure

- `agents/`: Contains `openai.yaml` which defines the UI integration (display name, short description, icon paths, and invocation policies).
- `assets/`: Contains the SVG icons used by the UI (`icon-small.svg`, `logo-large.svg`).
- `references/`: Contains playbook documentation and gotchas for the agent to read when invoked.
- `scripts/`: Contains the core PowerShell scripts used to communicate with the local Antigravity server.
- `tests/`: Contains test logic (if applicable).
- `SKILL.md`: The core metadata and prompt instructions for the skill. Must remain ASCII-safe to prevent cp950 errors on Windows systems.

## Installation

Run `_tmp_install_antigravity_skill.ps1` to copy the skill package to the global `~/.codex/skills/antigravity-gemini-bridge` folder. Re-running it will update the installed copy with the latest files from this repository.
