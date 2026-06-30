---
name: antigravity-gemini-bridge
description: Use when Codex needs to reconnect a locally logged-in Antigravity session, talk to Gemini through the standalone language server, run capability or multi-turn collaboration checks, or coordinate a shared workspace task where Codex plans and reviews while Gemini executes or brainstorms.
---

# Antigravity Bridge Codex

## Overview

Use this skill to let Codex collaborate with a locally logged-in Antigravity Gemini session as a second agent. Gemini is usually the primary writer or executor for the delegated task, while Codex remains responsible for scope control, supervision, review, and final acceptance.

## When To Use

Use this skill when the user wants any of these outcomes:

- reconnect to a fresh Antigravity session after app restart or reboot
- send prompts to Gemini through the local language server instead of the UI
- verify that local Gemini can read files, write files, browse the web, or keep multi-turn memory
- run a repeatable capability matrix before trusting a new session
- hold a multi-turn collaboration where Codex and Gemini both contribute to the same workspace task

Do not use this skill when:

- the user only needs ordinary web search or ordinary local coding with no Gemini collaboration
- Antigravity is not installed or the user is not logged in yet
- the task needs remote cloud APIs instead of the local Antigravity standalone app

## Platform Scope

- Windows and macOS are supported by the bundled discovery flow.
- Windows discovery defaults to `%APPDATA%\Antigravity\logs\main.log` and `%APPDATA%\Antigravity\logs\language_server.log`.
- macOS discovery first checks `~/Library/Logs/Antigravity/main.log` and `~/Library/Logs/Antigravity/language_server.log`, then falls back to the newest snapshot pair under `~/Library/Application Support/Antigravity/logs/`.
- Workspace binding supports Windows drive-letter paths and POSIX absolute paths.
- Linux, UNC paths, and WSL-style paths still require explicit human verification before relying on them.
- For script calls that start cascades or send messages, prefer `-Model` or `$env:ANTIGRAVITY_MODEL`. If neither is set, the bridge falls back to the newest real model id found in local Antigravity conversation storage, and when possible also reuses the matching internal `MODEL_PLACEHOLDER_M*` enum that Antigravity's planner actually expects.

## Workflow

Follow this order:

1. Confirm Antigravity standalone app is open and the user is logged in.
2. Reconnect the current session with `scripts/Discover-AntigravitySession.ps1`.
3. Use `scripts/Invoke-AntigravityRpc.ps1` to create a cascade and send messages.
4. Choose one operating mode:
   - quick smoke check
   - capability matrix
   - collaborative chat
5. If starting a fresh collaborative chat, send the intro only once on the first turn, and explicitly identify yourself as Codex before handing anything to Gemini.
6. Use the file handoff rule before file-related collaboration: if the exact files are known, give Gemini the file paths; if the exact files are not locked yet, name the expected file area or candidate files; only skip file handoff for pure discussion with no current local artifact.
7. If the user explicitly authorizes whole-workspace inspection, say that clearly to Gemini: this is the user's local workspace on the same machine through a locally logged-in Antigravity session, and Gemini should inspect the named workspace root locally, summarize the relevant areas first, then narrow down to the files that matter.
8. Default to the lowest Codex-token path: for large writing, bulk-edit work, or brainstorming, give Gemini only the high-level direction, scope boundaries, file paths, and acceptance checks first, then let Gemini produce the first pass.
9. Let Codex stay in the supervisor role: narrow the scope when Gemini drifts, remind Gemini of constraints, and perform the final review.
10. If the remaining task is small, localized, or faster to fix directly than to delegate, Codex may apply the edit itself instead of sending Gemini another turn.
11. Inspect Gemini's actual reply or artifacts before telling the user anything is done.

## Capability Recovery

If the current Codex thread does not expose a direct Antigravity bridge tool, do not assume Antigravity is broken. Recover in this order:

1. Use the bundled PowerShell wrapper when `pwsh` is available: `scripts/Invoke-AntigravityBridge.ps1`.
2. Use the Python fallback when PowerShell is unavailable or the thread only has ordinary shell access: `scripts/antigravity_bridge.py`.
3. Use the packaged MCP server when the plugin exposes tools from `.mcp.json`.
4. Rediscover the session from logs before every run; never reuse old ports or CSRF tokens.

Keep default CLI output compact. Only request full trajectories with `-Verbosity` or `--include-trajectory` when debugging, because raw trajectories can be very large.

## Privacy and Workspace Delegation

When delegating tasks across the bridge, strictly adhere to these data access boundaries:

1. Default to scoped delegation. When the task scope or user intent is unclear, use high-level delegation and do not automatically inspect or share local files.
2. Respect explicit authorization. If the user authorizes access to a specific repository, file path, or task scope, Gemini through Antigravity may inspect local files within that defined boundary.
3. Use least privilege. Share and inspect only the information needed for the immediate task, and avoid broad accidental disclosure such as whole disks, unrelated workspace roots, or unrelated private directories.
4. Keep Codex responsible for orchestration, supervision, and final review of the generated outputs.

## Operating Modes

### Quick Smoke Check

Use this when you only need to prove the session is alive.

```powershell
. "$PSScriptRoot\scripts\Invoke-AntigravityRpc.ps1"
$session = Get-AntigravitySessionInfo
$cascade = New-AntigravityCascade -WorkspacePaths @('/Volumes/MyGame') -Session $session
Send-AntigravityMessage -CascadeId $cascade.CascadeId -Text 'Please reply only BRIDGE_OK' -Session $session | Out-Null
$trajectory = Wait-AntigravityTrajectoryMatch -CascadeId $cascade.CascadeId -Pattern 'BRIDGE_OK' -Session $session
Get-LatestAntigravityPlannerResponseText -Trajectory $trajectory
```

### Capability Matrix

Use this before relying on a new session, after reboot, or after app restart.

```powershell
pwsh -NoLogo -NoProfile -File "$PSScriptRoot\scripts\Run-AntigravityCapabilityMatrix.ps1" -WorkspacePath /Volumes/MyGame
```

This runner is self-contained. It creates temporary probe files in the workspace and verifies:

- roundtrip reply
- workspace awareness
- reading an existing probe file
- writing a new file
- modifying an existing file
- multi-turn memory
- confirmed web search
- missing-model negative check

### Collaborative Chat

Use this when Codex wants a true back-and-forth discussion with Gemini.

Start a new conversation with:

```powershell
pwsh -NoLogo -NoProfile -File "$PSScriptRoot\scripts\Start-AntigravityConversation.ps1" -WorkspacePath /Volumes/MyGame -OpeningPrompt 'Let''s brainstorm the MVP for the phase 3 bridge CLI.'
```

Then continue from the returned `cascadeId` with `Send-AntigravityMessage`. For genuine improvised chat, read Gemini's actual previous reply first, then decide the next prompt from that reply instead of pre-writing every turn. In normal collaboration, let Gemini produce the first concrete draft or edit pass, and keep Codex in the supervisor role unless there is a good reason to take over directly.

When the conversation is about files in the workspace, do not make Gemini guess. Use this rule:

- if the exact files are already known, list the file paths and ask Gemini to inspect them first
- if the exact files are not locked yet, say that clearly and name the expected file area, candidate files, or document surfaces before asking for suggestions
- if the user has explicitly authorized a full-workspace inspection, name the workspace root, say that the inspection is for the same local machine through the locally logged-in Antigravity session, and ask Gemini to summarize the relevant areas before diving into specific files
- only treat it as pure discussion when there is no current local artifact to inspect

Gemini is often smart and imaginative, but can also miss details or forget part of the scope. Give Gemini the big direction, current file set or expected file area, goal, and acceptance checks, and when the user explicitly authorized whole-workspace inspection, say that the workspace is local to the same machine and ask for a summary-first pass before drilling into files. Then inspect the actual result carefully whenever precision matters.

Use `references/collaboration-playbook.md` for the intro style, turn-taking pattern, and improvised follow-up rules. Do not open with an anonymous task dump; Gemini should be able to tell that Codex is the speaker from the very first turn.

## Verification Rules

Never trust only the first surface you see.

After each run, verify one of these:

- `Get-LatestAntigravityPlannerResponseText` contains the expected marker
- `Get-LatestAntigravityErrorText` contains the expected failure string
- a created or modified file exists and contains the expected text
- the trajectory includes `CORTEX_STEP_TYPE_SEARCH_WEB` when claiming real web access

## Known Gotchas

Read `references/known-gotchas.md` before changing the flow. The most important pitfalls are:

- ports and CSRF token change when Antigravity restarts
- `GetCascadeTrajectory` must be read from `trajectory.steps[]`, not the old top-level fields
- planner model wiring is strict: the bridge may need both the public model id and the paired internal `MODEL_PLACEHOLDER_M*` enum, so prefer the helper scripts instead of hand-rolling the payload
- recent successful local conversation storage can be used as the last model fallback when no explicit model is passed, including the paired internal planner enum when available
- UI chat visibility is optional; successful background RPC does not guarantee a visible chat window

## Resources

- `scripts/Invoke-AntigravityBridge.ps1`: unified thin wrapper/CLI for discover, matrix, start, send, and trajectory commands (underlying capabilities are still provided by the existing scripts)
- `scripts/antigravity_bridge.py`: standard-library Python fallback for discover, start, send, trajectory, and smoke commands when `pwsh` or skill tools are unavailable
- `mcp/antigravity_bridge_server.py`: minimal stdio MCP server advertised by `.mcp.json` for tool-style recovery in plugin-capable Codex sessions
- `scripts/Discover-AntigravitySession.ps1`: reconnect from current logs
- `scripts/Invoke-AntigravityRpc.ps1`: create cascades, send messages, parse replies and errors
- `scripts/Run-AntigravityCapabilityMatrix.ps1`: repeatable end-to-end verification
- `scripts/Start-AntigravityConversation.ps1`: start a fresh collaborative conversation with one-time intro
- `references/collaboration-playbook.md`: intro tone, multi-turn collaboration pattern, improvisation rules
- `references/known-gotchas.md`: failure modes and compatibility notes
