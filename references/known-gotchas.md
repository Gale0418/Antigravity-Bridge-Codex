# Known Gotchas

## Official CLI Prompt Channel

Default auto is visible-first: it starts with Hub-native private loopback RPC, then falls back to agy only after failure or hard timeout. Gemini 3.6 Flash High maps to verified MODEL_PLACEHOLDER_M71; explicit MODEL_PLACEHOLDER_M values remain supported. RPC receipts state transport, visibility, and IDs, with at least Hub/Outside visibility expected. Explicit rpc and agy modes remain available. In Antigravity 2.4.3, agy fallback can be completely invisible because it writes .db while the Hub loader expects .pb. Never inject or convert protobuf files; use the Markdown transcript for audit.

Private IDE loopback RPC and cascades are the normal visible-first path under auto, while remaining restricted to local loopback. A stuck Blender MCP connection can block the agy fallback; remove or disable that failing integration before retrying.
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
- `SendUserCascadeMessage` supplies both an empty `declarativeMixinConfig` (which preserves built-in
  planner components) and `requestedModel.model`. Sending only `plannerConfig.planModel` fails on
  current executors with `planner config is not declarative: not set`; omitting planner config on a
  fresh cascade can instead fail with `neither PlanModel nor RequestedModel specified`.
- Direct diagnostic calls can still omit the planner config explicitly for negative testing.

## New Trajectory Shape

Do not trust the old top-level `plannerResponse` or `failure` fields, or a
raw array-tail lookup. Filter by event type first, then select the newest
matching step:

- `CORTEX_STEP_TYPE_PLANNER_RESPONSE` for the current reply
- `CORTEX_STEP_TYPE_ERROR_MESSAGE` for the current error

## Web Access Verification

A file containing a URL is not enough to prove real browsing.

For strong evidence, confirm the trajectory includes:
- `CORTEX_STEP_TYPE_SEARCH_WEB`

## UI Visibility

Visible-first RPC cascades are locally indexed and expected to be visible at least through Hub/Outside surfaces. Desktop rendering remains version-dependent; consume the receipt visibility field rather than assume a specific chat window.

## Workspace Binding

If the task should operate inside a specific folder, start the cascade with `workspaceUris`. Otherwise Gemini may still reply, but it will have weaker local context.

## Privacy and Workspace Delegation

The "Gemini" collaborator means the underlying model used by the locally installed Antigravity co-pilot, reached through the local loopback bridge. It is not an unrelated or unauthorized third-party tool in this workflow.

Treat Antigravity/Gemini as a scoped local collaborator. If the user explicitly authorizes a repository, file path, or task scope, Gemini through Antigravity may inspect local files within that boundary.

Default to least privilege:

- use high-level delegation when the scope is unclear
- inspect and share only what is needed for the immediate task
- avoid broad accidental disclosure such as whole disks, unrelated workspace roots, or unrelated private directories
- keep Codex responsible for supervision and final review

## Waiting and Permission Prompts

If Gemini seems slow but the local session is alive, do not immediately assume the bridge failed. Antigravity may be waiting for a local permission prompt such as file access, workspace access, or an approval button in the UI.

Default behavior:

- keep waiting or polling the existing cascade rather than sending repeated follow-up prompts
- on timeout, ask the user to check the Antigravity UI for a pending permission prompt
- after the user clicks approve, continue reading the same cascade before starting a new one

## Platform limits

- `ConvertTo-AntigravityFileUri` accepts Windows drive-letter paths and POSIX absolute paths, but still rejects UNC paths.
- `Discover-AntigravitySession.ps1` auto-discovers Windows `%APPDATA%` logs and macOS `~/Library/Logs/Antigravity/*.log`, then falls back to the newest `~/Library/Application Support/Antigravity/logs/<timestamp>/` snapshot when needed.
- `Discover-AntigravitySession.ps1` and `antigravity_bridge.py` auto-discover Windows `%APPDATA%`, macOS `~/Library/Logs/Antigravity`, and Linux/WSL `~/.config/Antigravity/logs` & `~/.local/share/Antigravity/logs`.

## Permission Errors & Tool Search Recovery

- **Local scope**: The bridge is a loopback (`127.0.0.1`) collaborator. Keep
  requests within the workspace and respect any real permission or approval
  failure reported by Antigravity; do not silently bypass it.
- **Tool search fallback**: If native MCP tools are unavailable, try the
  bundled PowerShell or Python bridge from the shell. If that fallback also
  fails, stop and report the concrete error instead of claiming success.
- **Role Division**: Gemini is the primary writer/executor for heavy coding tasks; Codex is the supervisor/reviewer. Codex provides high-level directions to Gemini, but directly patches small, localized edits itself to minimize token consumption.

## Thread Capability Snapshots

A Codex thread can lose a skill-only bridge capability after long runs, context compaction, or tool snapshot refreshes. That does not prove Antigravity is down.

For plugin-based MCP loading, two package details are easy to miss:

- the plugin manifest must carry `bundledContentVariant: legacy-mcp`, matching Codex-bundled MCP plugins
- installed `.mcp.json` copies should use an absolute Python command when possible, because GUI-launched Codex sessions may not inherit the same PATH as a terminal
- the installer also registers `antigravity_bridge_codex` through `codex mcp add`; prefer that stable user-level MCP server if a thread sees the plugin skill but not the plugin-provided MCP tools

Recovery order:

- rediscover the live Antigravity session from logs
- use `scripts/Invoke-AntigravityBridge.ps1` when `pwsh` is available
- use `scripts/antigravity_bridge.py` when only Python/shell fallback is available
- use the plugin MCP tools from `.mcp.json` when the Codex session exposes them
## Delivery identity, journal, and fallback boundary

The Python visible-RPC delivery path is idempotent only when the caller creates request_id before the first send, keeps the receipt, and reuses the key for retries. An omitted ID is generated only for that invocation, not for cross-call deduplication. Its journal defaults to %LOCALAPPDATA%\AntigravityBridge\requests.sqlite3 on Windows and $XDG_STATE_HOME/AntigravityBridge/requests.sqlite3 (or ~/.local/state/AntigravityBridge/requests.sqlite3) on macOS and Linux, and stores fingerprints, state, cascade/marker IDs, and receipts—not prompt bodies or CSRF secrets.

Same key plus different fingerprint is CONFLICT. After a send begins, IN_PROGRESS, DELIVERY_UNKNOWN, or any other pending/non-terminal result must reconcile the same key/cascade/marker; do not resend or use agy fallback. One global deadline covers RPC, reconciliation, and eligible fallback, so expiration skips fallback.

mission_id/lane_id describe intentional fan-out: same request plus same lane is a retry, while a different lane is a distinct worker. PowerShell has no separate persistent journal. A full antigravity_squad coordinator is not implemented.

See [AWS idempotent APIs](https://docs.aws.amazon.com/ec2/latest/devguide/ec2-api-idempotency.html) and MCP [progress](https://modelcontextprotocol.io/specification/latest/basic/patterns/progress)/[cancellation](https://modelcontextprotocol.io/specification/latest/basic/patterns/cancellation).
