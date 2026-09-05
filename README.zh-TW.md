# Antigravity Bridge Codex

![Version](https://img.shields.io/badge/version-0.2.1-20B2AA) ![Rust](https://img.shields.io/badge/Rust-1.98.1-DEA584) ![License](https://img.shields.io/badge/license-MIT-blue)

**讓 Codex 與使用者本機已登入的 Antigravity / Gemini 進行「看得懂進度」的安全協作。**

[English](README.md)

## 0.2.x 最重要的改變

以前最容易出事的是：Gemini 還在查資料、跑工具或整理大型內容，Codex 卻只看到「還沒回最終答案」，於是誤判妹妹失聯，甚至直接讓 Luna 接手同一個 workspace。

現在橋樑改成 **progress-aware watchdog**：只要 trajectory、搜尋、工具事件、檔案工作或 planner response 還有實質進展，就會刷新 idle watchdog。沒有最終文字回覆，**不等於** stalled。

Installer 也會在 `$CODEX_HOME/AGENTS.md` 管理一段窄範圍 trust capsule：只要是透過本橋樑、且仍在使用者已授權的任務 / workspace 範圍內，Codex 不必再因為協作者叫 Gemini / Antigravity 就重問一次「是否授權委派」。真正的登入、OS、sandbox、UI、提權或擴大存取範圍仍然是獨立權限事件。

## 架構真相

這個 repository 現在是 **Hybrid 架構**，不是已經 100% 純 Rust。

```text
Codex / MCP
    │
    ├─ progress-aware orchestration ──> scripts/antigravity_bridge_v2.py
    │                                      │
    │                                      ├─ Rust 1.98.1 abc-supervisor
    │                                      └─ handoff / watchdog policy
    │
    └─ compatibility transport ───────> scripts/antigravity_bridge.py
                                           │
                                           ├─ localhost Antigravity RPC
                                           ├─ delivery journal / idempotency
                                           ├─ session discovery
                                           └─ agy fallback
```

Rust 1.98.1 負責新的 progress state model 與 supervisor；成熟的 Python transport 則刻意保留，繼續負責 localhost private RPC、request journal、session discovery 與既有 delivery semantics。這些核心不會為了「看起來全 Rust」而一次硬翻，避免把已驗證的安全性一起翻掉。

## 核心保證

- **進度感知等待：** 搜尋、工具、trajectory 或回覆增量都會延長 idle budget。
- **不再用沉默判死刑：** 沒有 final reply 不是 stalled 的充分條件。
- **保留 at-most-once：** 投遞狀態不明時，不允許換 transport 重送同一工作。
- **第二 writer fencing：** `DELIVERY_UNKNOWN`、`ACCEPTED_PENDING`、`INPUT_REQUIRED`、`PREPARING`、`IN_PROGRESS`、`DELIVERING` 都不准 Luna 或其他 writer 在同一 workspace 接管。
- **Handoff 明確化：** receipt 會暴露 `supervisor_state`、`may_handoff_read`、`may_handoff_write`、`remote_may_resume`。
- **授權範圍收斂：** trust capsule 只覆蓋本 bridge 與當前使用者已授權的 task/workspace。
- **真正權限不會被吃掉：** 登入失效、OS / sandbox、Antigravity UI、提權或擴大 scope 仍要照規則處理。
- **不假裝全本機：** bridge transport 是 localhost；實際模型 inference 仍可能由外部模型服務提供。

## 狀態模型

| 狀態 | 意義 | 同 workspace writer 接班 |
| --- | --- | --- |
| `ACTIVE` | 持續觀察到有效進度 | 不可 |
| `QUIET` | 暫時沒新事件，但還在 idle budget 內 | 不可 |
| `SUSPECT` | 安靜較久，需要提高警覺 | 不可 |
| `ACTIVE_PENDING` | 本回合 response slice 結束，但工作仍活著 | 不可 |
| `INPUT_REQUIRED` | 真正 runtime / login / UI 權限事件 | 不可 |
| `DELIVERY_UNKNOWN` | 請求可能已被接受 | 不可 |
| `STALLED` | 超過 adaptive idle threshold 都沒有有效進度 | 只有 receipt 同時證明 write-safe 才可 |
| `DONE` | 完成 marker 已出現 | 只做 review / follow-up |

`may_handoff_read` 可以在 `may_handoff_write = false` 時仍為 true，因此 Luna 可以先做唯讀 warm standby / review，但不會跟 Gemini 同時改同一份 workspace。

## 安裝

### macOS / Linux

```bash
python3 scripts/install_v2.py
```

### Windows / PowerShell 7

```powershell
pwsh -NoLogo -NoProfile -File .\scripts\install-v2.ps1
```

Installer 會：

1. 執行已驗證的 compatibility installer；
2. 把 Rust workspace 同步進已安裝 skill / plugin；
3. 若找到**精確的 Rust/Cargo 1.98.1**，先 build `abc-supervisor`；
4. 把 binary 安裝到 package 的 `bin/`；
5. 以 marker 管理 `$CODEX_HOME/AGENTS.md` 的 trust capsule，不覆寫使用者原本內容。

如果機器沒有 Rust 1.98.1，安裝仍可使用 Python compatibility watchdog，並明確顯示 native supervisor 沒有啟用，不會假裝 build 成功。

## 主要使用方式

一般工作請走新版入口：

```bash
python3 scripts/antigravity_bridge_v2.py prompt \
  --prompt "請檢查目前 workspace 並整理相關檔案。" \
  --workspace-path .
```

Smoke check：

```bash
python3 scripts/antigravity_bridge_v2.py smoke --workspace-path .
```

`.mcp.json` 的正式 MCP 入口目前是：

```text
mcp/antigravity_bridge_server_v2.py
```

其他舊 Python / PowerShell scripts 現在屬於 **compatibility / diagnostic surface**，不是推薦的 orchestrator front door。

## 角色分工

預設：

- **Gemini / Antigravity：** Creative Scout、主要重工作 writer / executor、負責大份第一版。
- **Codex：** planner、scope controller、reviewer、最終 acceptance gate。
- **Luna / 其他 worker：** bounded finisher / reviewer；只有 bridge 明確標記 write-safe 才能接手同一 workspace 寫入。

Gemini 說「完成」也不是完成證據；Codex 仍必須檢查檔案、receipt、test output 或其他可驗證 artifact 才能向使用者宣布完成。

## 權限邊界

Trust capsule 的意思是：

> 「對這個使用者已授權的 task/workspace，Codex 可以透過本機已登入的 Antigravity bridge 進行委派，不必只因協作者叫 Gemini 就再問一次概念性授權。」

它**不代表**：

- 所有 Gemini 服務永久全域可信；
- bridge 可以看無關資料夾；
- 模型推論保證不離開裝置；
- OS、sandbox、登入、提權或 Antigravity UI 權限可以跳過。

## 驗證

0.2.x orchestration Python regression：

```bash
python3 -m unittest tests/test_progress_watchdog.py tests/test_install_v2.py
```

有 Rust 1.98.1 時再跑：

```bash
cargo +1.98.1 fmt --manifest-path rust/Cargo.toml --all -- --check
cargo +1.98.1 check --manifest-path rust/Cargo.toml --workspace --all-targets --locked
cargo +1.98.1 test --manifest-path rust/Cargo.toml --workspace --all-targets --locked
```

本專案不把 GitHub Actions 當 acceptance gate；維護時以本機驗證 + 遠端 commit SHA 實際確認為準。

## Repository 地圖

```text
.
├── SKILL.md                         # Codex canonical operating contract
├── agents/openai.yaml              # Invocation / orchestration policy
├── mcp/
│   ├── antigravity_bridge_server_v2.py  # 主要 MCP adapter
│   └── antigravity_bridge_server.py     # compatibility MCP framing
├── scripts/
│   ├── antigravity_bridge_v2.py     # 主要 progress-aware CLI
│   ├── antigravity_bridge.py        # 成熟 compatibility transport/journal
│   ├── install_v2.py                # 主要 installer
│   └── install.py                   # compatibility installer
├── rust/
│   ├── abc-core/
│   ├── abc-supervisor/
│   └── rust-toolchain.toml          # Rust 1.98.1
└── references/
    ├── progress-aware-supervisor.md
    ├── delegation-contract.md
    ├── collaboration-playbook.md
    ├── known-gotchas.md
    ├── streaming-event-protocol.md
    ├── verification-gate.md
    └── skill-packaging.md
```

## 維護者硬規則

不要為了讓 failover 看起來更快，就把 `safe_to_fallback = false` 或 same-workspace writer fencing 放寬。**Transport fallback（RPC → agy）與 Agent handoff（Gemini → Luna）是兩個不同決策，安全條件也不同。**

## License

MIT
