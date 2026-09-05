# Known Gotchas

This file records current operational pitfalls for the 0.2.x hybrid bridge. Historical implementation notes belong in Git history, not here.

## 1. Silence is not a stall

The most important rule in 0.2.x:

> A missing final reply is not enough evidence that Antigravity stopped working.

Long searches, tool calls, file operations, and planner-response growth count as meaningful progress. Use the v2 supervisor state and receipt facts instead of a wall-clock-only timeout.

- `ACTIVE`, `QUIET`, `SUSPECT`, `ACTIVE_PENDING` → do not replace the writer.
- `INPUT_REQUIRED` → handle the real runtime/login/UI permission event, then continue the same cascade.
- `DELIVERY_UNKNOWN` / `ACCEPTED_PENDING` → the request may already be accepted; never resend or create a same-workspace second writer.
- `STALLED` alone still does not prove write takeover is safe; require `may_handoff_write = true`.

## 2. Transport fallback and agent handoff are different

`safe_to_fallback` answers whether the same Gemini request may use another **transport**.

`may_handoff_write` answers whether another **agent** may write the same workspace.

Do not use one as a substitute for the other. A fast fallback is not worth duplicate execution or competing edits.

## 3. Session data is dynamic

Antigravity restarts can rotate:

- CSRF token;
- HTTPS port;
- HTTP port;
- language-server PID;
- log snapshot paths.

Rediscover current session information from logs. Do not persist and reuse old ports/tokens as configuration.

## 4. The compatibility Python layer is still required

The repository is not yet pure Rust.

Primary orchestration:

```text
scripts/antigravity_bridge_v2.py
```

Still-required compatibility responsibilities:

```text
scripts/antigravity_bridge.py
  ├─ localhost RPC
  ├─ request journal / idempotency
  ├─ session discovery
  └─ agy fallback
```

Similarly, the primary MCP adapter still reuses the mature compatibility MCP framing server. Do not delete these files merely because their filenames look older.

## 5. Rust supervisor availability is explicit

`rust/rust-toolchain.toml` pins Rust 1.98.1.

The installer only enables the native `abc-supervisor` when the exact Cargo/Rust 1.98.1 toolchain is available and the release build succeeds. Otherwise the Python compatibility watchdog remains active and the installer reports native supervision as inactive.

Never claim a Rust build passed if the toolchain was not actually available.

## 6. Trajectory shape matters

Use `trajectory.steps[]`; do not rely on old top-level response/error fields or assume the final array element is the planner answer.

Important event types include:

- `CORTEX_STEP_TYPE_PLANNER_RESPONSE`
- `CORTEX_STEP_TYPE_ERROR_MESSAGE`
- search/tool/browser/command/file-related events used by the progress signature

Raw trajectories can be large. Keep them out of normal receipts unless debugging.

## 7. Model wiring can be version-sensitive

Antigravity executors may require both a public model id and an internal planner enum (`MODEL_PLACEHOLDER_M*`). Prefer the compatibility transport's model-selection helpers rather than hand-rolling payloads.

A model error is not evidence that delivery was never attempted. Respect the receipt's delivery state before deciding whether fallback or retry is safe.

## 8. `agy` visibility is not equivalent to Hub-native RPC

The normal `auto` path prefers the Hub-native localhost RPC transport. `agy` is a fallback only when the RPC attempt is proven safe to fall back.

Desktop/Hub visibility can vary by Antigravity version. Consume the receipt's visibility evidence instead of assuming every successful request appears in the same UI surface.

## 9. Workspace binding must stay explicit

Bind the intended workspace and keep delegation scoped to the user's authorized task/repository.

Do not broaden access to:

- unrelated repositories;
- home-directory contents;
- whole disks;
- unrelated private directories.

The trust capsule pre-authorizes delegation through this bridge for the current user-granted task/workspace; it does not expand the scope.

## 10. Localhost does not mean local inference

The bridge transport to Antigravity is localhost (`127.0.0.1`). That does not prove the configured model inference stays on-device.

Do not document or tell the user that all data remains strictly local unless the configured inference stack independently guarantees that.

## 11. Conceptual delegation permission is separate from runtime permission

Do not repeatedly ask whether Codex may “use Gemini” through this bridge when the user has already authorized the current task/workspace.

Still surface real permission events such as:

- expired login;
- Antigravity UI approval;
- OS/sandbox denial;
- sudo/elevation;
- scope expansion beyond the authorized workspace.

## 12. Delivery identity must survive retries

The visible RPC path is idempotent only when the caller keeps the original `request_id` and receipt.

Rules:

- same key + same fingerprint → reconcile/replay;
- same key + different fingerprint → `CONFLICT`;
- after send begins, pending or ambiguous states reconcile the same cascade/marker;
- do not mint a new request ID merely because the current response slice ended.

The journal stores delivery metadata and sanitized receipts, not prompt bodies or CSRF secrets.

## 13. Lane cancellation is not remote cancellation

A local lane marked cancelled/fenced only changes bridge coordination. It does not prove that a previously dispatched Antigravity task stopped running.

Therefore local lane cancellation alone must never authorize a same-workspace replacement writer.

## 14. GUI recovery must be conservative

Do not open another Antigravity GUI process when an existing process may still be alive or warming up. Do not kill/restart a process unless ownership is proven and no pending delivery can be harmed.

## 15. MCP/tool snapshots can disappear without Antigravity being down

A Codex thread can lose a tool snapshot after compaction or session changes. Recovery order:

1. use the installed v2 MCP route if available;
2. use `scripts/antigravity_bridge_v2.py` from the local package/workspace;
3. let the v2 front door reuse the compatibility transport;
4. only then report a concrete bridge failure.

Tool absence by itself is not proof that Antigravity is offline.

## 16. Remote persistence must be verified remotely

When maintenance work is supposed to reach GitHub `main`, do not trust a local commit, temp directory, patch file, or summary.

Verify the actual remote branch SHA and changed-file list before claiming completion.
