# Changelog

## 0.2.1 - 2026-09-05

- Rewrote English and Traditional Chinese READMEs around the actual 0.2.x hybrid architecture.
- Replaced the stale SKILL workflow with the progress-aware supervisor, scoped trust, and safe handoff contract.
- Updated packaging documentation to distinguish primary v2 entry points from intentionally retained compatibility transport files.
- Removed obsolete July implementation plans/specs, redundant workflow/examples docs, temporary strict-review notes, and visual-only identity notes.
- Removed the obsolete Pester GitHub Actions workflow; local verification plus explicit remote commit verification remain the maintenance acceptance gate.
- Clarified that the project is not yet a pure-Rust rewrite: Rust 1.98.1 owns supervisor/policy while mature Python remains responsible for proven transport/journal semantics.

## 0.2.0 - 2026-09-05

- Added Rust 1.98.1 `abc-core` and persistent `abc-supervisor` watchdog.
- Added progress-aware trajectory waiting so long searches/tool runs do not become false stalls.
- Added explicit read/write handoff safety facts and fenced ambiguous deliveries from same-workspace takeover.
- Added v2 MCP adapter without duplicating the mature MCP framing implementation.
- Added marker-scoped, idempotent task-level delegation trust capsule installer.
- Added Luna/secondary-writer routing guidance to `agents/openai.yaml`.
- Kept mature Python private RPC and delivery journal as a compatibility transport rather than performing an unsafe big-bang rewrite.
