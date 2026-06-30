# Known Gotchas

## Dynamic Session Data

Antigravity standalone app can restart and rotate all of these:

- CSRF token
- HTTPS port
- HTTP port
- language server pid

Always rediscover them from logs instead of reusing an old value.

## Required Model Field

Do not rely on a hardcoded placeholder. Prefer `-Model` or `$env:ANTIGRAVITY_MODEL`, and otherwise let the bridge fall back to the newest real model id found in local Antigravity conversation storage.

The local executor currently accepts one of these planner paths:

```json
{
  "requestedModel": "MODEL_PLACEHOLDER_M36",
  "cascadeConfig": {
    "plannerConfig": {
      "planModel": "MODEL_PLACEHOLDER_M36"
    }
  }
}
```

When no internal enum mapping is discoverable, the bridge falls back to the older explicit model-id path:

```json
{
  "cascadeConfig": {
    "plannerConfig": {
      "requestedModel": {
        "model": "your-real-model-id"
      }
    }
  }
}
```

If both planner paths are missing or the payload uses the wrong field shape, expect:

```text
failed to construct executor: neither PlanModel nor RequestedModel specified. You must specify a valid model.
```

If Antigravity shows `Agent execution terminated due to error` with that exact failure, the request reached the local executor but no real planner model survived the payload path.

Current macOS/Windows bridge behavior:

- top-level `StartCascade.requestedModel` prefers the paired internal enum such as `MODEL_PLACEHOLDER_M36` when a recent successful local conversation exposes it
- `SendUserCascadeMessage.cascadeConfig.plannerConfig.planModel` also prefers that internal enum
- when no enum mapping is discoverable, the bridge falls back to the older explicit model-id path

## New Trajectory Shape

Do not trust the old top-level `plannerResponse` or `failure` fields.

Read the current reply from the last step of type:
- `CORTEX_STEP_TYPE_PLANNER_RESPONSE`

Read the current error from the last step of type:
- `CORTEX_STEP_TYPE_ERROR_MESSAGE`

## Web Access Verification

A file containing a URL is not enough to prove real browsing.

For strong evidence, confirm the trajectory includes:
- `CORTEX_STEP_TYPE_SEARCH_WEB`

## UI Visibility

Background RPC success does not imply the Antigravity chat window will visibly open. The local language server can process a cascade entirely in the background.

## Workspace Binding

If the task should operate inside a specific folder, start the cascade with `workspaceUris`. Otherwise Gemini may still reply, but it will have weaker local context.

## Privacy and Workspace Delegation

Treat Antigravity/Gemini as a scoped local collaborator. If the user explicitly authorizes a repository, file path, or task scope, Gemini through Antigravity may inspect local files within that boundary.

Default to least privilege:

- use high-level delegation when the scope is unclear
- inspect and share only what is needed for the immediate task
- avoid broad accidental disclosure such as whole disks, unrelated workspace roots, or unrelated private directories
- keep Codex responsible for supervision and final review

## Platform limits

- `ConvertTo-AntigravityFileUri` accepts Windows drive-letter paths and POSIX absolute paths, but still rejects UNC paths.
- `Discover-AntigravitySession.ps1` auto-discovers Windows `%APPDATA%` logs and macOS `~/Library/Logs/Antigravity/*.log`, then falls back to the newest `~/Library/Application Support/Antigravity/logs/<timestamp>/` snapshot when needed.
- Linux and WSL layouts are still not auto-detected; pass explicit log paths before trusting them.

## Thread Capability Snapshots

A Codex thread can lose a skill-only bridge capability after long runs, context compaction, or tool snapshot refreshes. That does not prove Antigravity is down.

Recovery order:

- rediscover the live Antigravity session from logs
- use `scripts/Invoke-AntigravityBridge.ps1` when `pwsh` is available
- use `scripts/antigravity_bridge.py` when only Python/shell fallback is available
- use the plugin MCP tools from `.mcp.json` when the Codex session exposes them
