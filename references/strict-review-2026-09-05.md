# Independent strict review — 2026-09-05

Reviewer prompt (verbatim):

> 不要相信前一輪結論，重新從正確性、回歸風險、效能、安全、資源使用與可維護性挑毛病，按照Mission Center標出待修優先度，只有真的沒有值得修的 P2 以上問題才准通過。

## Review loop

### Round 1

- **P1 — Rust supervisor pipe could block without explicit stdout flush.** Fixed by flushing after every READY/STATE response.
- **P2 — Per-cascade in-memory supervisor cache was unbounded.** Fixed with a 256-entry cap.
- **P2 — Source-tree release binary could be executed implicitly.** Fixed: installed `bin/abc-supervisor` is the normal candidate; source `rust/target/release` requires `ANTIGRAVITY_BRIDGE_DEV_RUST=1`.
- **P2 — Fixed 3-second polling would repeatedly transfer growing trajectories during long research.** Fixed with bounded adaptive polling up to 10 seconds based on EWMA event gaps.
- **P2 — v2 installer could discover malformed AGENTS markers only after legacy installation mutated files.** Fixed with a fail-closed preflight before installation.
- **P2 — legacy installer stamps installed plugin as 0.1.0.** Fixed in v2 wrapper by restamping 0.2.0 and refreshing the local plugin registration.

### Round 2

Re-reviewed correctness, regression risk, performance, security, resource use, and maintainability after fixes.

**PASS: no remaining P0/P1/P2 issue identified in the v2 change set.**

Known non-blocking limitation: the mature private RPC and delivery journal remain in the Python compatibility transport. The Rust boundary intentionally owns progress/handoff supervision first; a later transport port should only replace Python after parity tests prove idempotency and delivery-ambiguity behavior.
