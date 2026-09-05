# Changelog

## 0.2.0 - 2026-09-05

- Added Rust 1.98.1 `abc-core` and persistent `abc-supervisor` watchdog.
- Added progress-aware trajectory waiting so long searches/tool runs do not become false stalls.
- Added explicit read/write handoff safety facts and fenced ambiguous deliveries from same-workspace takeover.
- Added v2 MCP adapter without duplicating the mature MCP framing implementation.
- Added marker-scoped, idempotent task-level delegation trust capsule installer.
- Added Luna/secondary-writer routing guidance to `agents/openai.yaml`.
- Kept mature Python private RPC and delivery journal as a compatibility transport rather than performing an unsafe big-bang rewrite.
