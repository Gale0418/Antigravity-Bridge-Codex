---
name: antigravity-gemini-bridge
description: Use when Codex needs to reconnect a locally logged-in Antigravity session, talk to Gemini through the standalone language server, run capability or multi-turn collaboration checks, or coordinate a shared workspace task where Codex plans and reviews while Gemini executes or brainstorms.
---

# Antigravity Gemini Bridge

## Overview

Use this skill to let Codex collaborate with a locally logged-in Antigravity Gemini session as a second agent. Codex remains the planner, reviewer, and final acceptance gate; Gemini becomes the local collaborator for execution, brainstorming, or back-and-forth discussion.

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

## Workflow

Follow this order:

1. Confirm Antigravity standalone app is open and the user is logged in.
2. Reconnect the current session with `scripts/Discover-AntigravitySession.ps1`.
3. Use `scripts/Invoke-AntigravityRpc.ps1` to create a cascade and send messages.
4. Choose one operating mode:
   - quick smoke check
   - capability matrix
   - collaborative chat
5. If starting a fresh collaborative chat, send the intro only once on the first turn.
6. Inspect Gemini's actual reply or artifacts before telling the user anything is done.

## Operating Modes

### Quick Smoke Check

Use this when you only need to prove the session is alive.

```powershell
. "$PSScriptRoot\scripts\Invoke-AntigravityRpc.ps1"
$session = Get-AntigravitySessionInfo
$cascade = New-AntigravityCascade -WorkspacePaths @('D:\MyGame') -Session $session
Send-AntigravityMessage -CascadeId $cascade.CascadeId -Text 'Please reply only BRIDGE_OK' -Session $session | Out-Null
$trajectory = Wait-AntigravityTrajectoryMatch -CascadeId $cascade.CascadeId -Pattern 'BRIDGE_OK' -Session $session
Get-LatestAntigravityPlannerResponseText -Trajectory $trajectory
```

### Capability Matrix

Use this before relying on a new session, after reboot, or after app restart.

```powershell
pwsh -NoLogo -NoProfile -File "$PSScriptRoot\scripts\Run-AntigravityCapabilityMatrix.ps1" -WorkspacePath D:\MyGame
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
pwsh -NoLogo -NoProfile -File "$PSScriptRoot\scripts\Start-AntigravityConversation.ps1" -WorkspacePath D:\MyGame -OpeningPrompt 'Let''s brainstorm the MVP for the phase 3 bridge CLI.'
```

Then continue from the returned `cascadeId` with `Send-AntigravityMessage`. For genuine improvised chat, read Gemini's actual previous reply first, then decide the next prompt from that reply instead of pre-writing every turn.

Use `references/collaboration-playbook.md` for the intro style, turn-taking pattern, and improvised follow-up rules.

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
- omitting `cascadeConfig.plannerConfig.requestedModel` causes a deterministic failure
- UI chat visibility is optional; successful background RPC does not guarantee a visible chat window

## Resources

- `scripts/Discover-AntigravitySession.ps1`: reconnect from current logs
- `scripts/Invoke-AntigravityRpc.ps1`: create cascades, send messages, parse replies and errors
- `scripts/Run-AntigravityCapabilityMatrix.ps1`: repeatable end-to-end verification
- `scripts/Start-AntigravityConversation.ps1`: start a fresh collaborative conversation with one-time intro
- `references/collaboration-playbook.md`: intro tone, multi-turn collaboration pattern, improvisation rules
- `references/known-gotchas.md`: failure modes and compatibility notes
