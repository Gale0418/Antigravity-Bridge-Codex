# Antigravity Bridge Codex 雙 AI 協作橋接套件

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![AI Integration](https://img.shields.io/badge/AI-Codex%20%2B%20Gemini-orange.svg)]()

**Antigravity Bridge Codex** 是一套開源的跨 AI 協作橋接 Skill 與 Plugin。它能讓 **Codex**（基於 GPT 的 CLI / IDE 助理）與本機正在執行的 **Antigravity**（基於 Gemini 的桌面應用程式）進行無縫雙向通訊與協同工作。

在協作架構中，Codex 擔任監督者與稽核者。預設 auto 採可見性優先：先走 Hub-native 私有環回 RPC，只有確認尚未派發的失敗才可 fallback 到 agy；已接受或交付不明時絕不 fallback。仍可明確指定 rpc 或 agy。

---

## 💡 核心特色

- **自動化 Session 偵測**：自動掃描系統日誌（Log），於 Windows、macOS 與 Linux/WSL 上自動提取 Antigravity 服務端口（Port）與 CSRF Token。
- **可見性優先通道**：`auto` 先建立 Hub-native RPC 對話，失敗才 fallback 到官方 `agy`；receipt 會揭露 transport、visibility、ID 與續聊語意。
- **全平台與雙語言腳本支援**：原生支援 PowerShell 7+ 與 Python 3.8+，兼具效能與跨平台彈性。
- **模型選擇**：讀取官方 `agy --output-format json models` 目錄，依顯式參數／環境變數／目錄／近期對話／安全預設排序，並保留已驗證的 RPC 相容 fallback。
- **健康與協調**：提供唯讀 health、保守熔斷器，以及 opt-in SQLite lane lease；支援 owner/epoch fencing、配額、取消與安全恢復決策。
- **MCP Server 整合**：提供 Model Context Protocol (MCP) 伺服器設定（`.mcp.json`），方便支援 MCP 的開發環境直接呼叫。
- **權限範圍與隱私**：明確限制工作區；主要 RPC 只走本機環回，fallback 則沿用本機已登入的官方 `agy`。

---

## 🏗️ 架構示意圖

```text
 ┌──────────────────────────────────────────────────────────┐
 │                      本機開發者工作區                     │
 └────────────────────────────┬─────────────────────────────┘
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
   ┌───────────────────┐             ┌───────────────────┐
   │   Codex (GPT)     │             │ Antigravity (App) │
   │ 任務監督與品質審查 │             │ Gemini 執行與撰寫 │
   └─────────┬─────────┘             └─────────┬─────────┘
             │                                 │
             │ auto：Hub RPC → agy fallback    │
             └──────────────► ◄────────────────┘
```

---

## 🚀 快速開始與安裝

### 選項 1：PowerShell 安裝與使用 (Windows / macOS / Linux)

執行自動化安裝腳本：

```powershell
pwsh -ExecutionPolicy Bypass -File ./scripts/install.ps1
```

需要底層診斷時，可手動偵測本機 Session 並透過私有 IDE RPC 發送測試訊息：

```powershell
. ./scripts/Discover-AntigravitySession.ps1
$session = Get-AntigravitySessionInfo
$cascade = New-AntigravityCascade -WorkspacePaths @($PWD.ProviderPath) -Session $session
Send-AntigravityMessage -CascadeId $cascade.CascadeId -Text "Hello from Codex!" -Session $session
```

### 選項 2：Python 跨平台 CLI 工具

執行 Python 安裝腳本：

```bash
python3 scripts/install.py
```

透過 CLI 直接傳送任務：

```bash
python3 scripts/antigravity_bridge.py prompt --prompt "檢查 main.py 是否有程式漏洞" --workspace-path "." --model "gemini-3.6-flash-high"
```

---

## 📂 專案目錄結構 (示意)

```text
antigravity-bridge-codex/
├── .codex-plugin/           # Codex 外掛定義檔
├── .mcp.json                # MCP Server 設定檔
├── SKILL.md                 # Agent 提示詞規範與工作流指引
├── README.md                # 英文說明文件
├── README.zh-TW.md          # 繁體中文說明文件
├── agents/                  # 子 Agent 角色定義檔
├── mcp/                     # MCP 服務啟動器與工具
├── references/              # 通訊協定規範與設計文件
├── scripts/
│   ├── Discover-AntigravitySession.ps1  # Session 自動偵測腳本
│   ├── Invoke-AntigravityBridge.ps1     # 高階橋接呼叫器
│   ├── Invoke-AntigravityRpc.ps1        # 底層 RPC 客戶端
│   ├── Run-AntigravityCapabilityMatrix.ps1 # 能力測試陣列
│   ├── antigravity_bridge.py            # Python 橋接主程式與庫
│   ├── install.ps1                      # PowerShell 安裝腳本
│   └── install.py                       # Python 安裝腳本
├── skills/
│   └── antigravity-bridge-codex/
│       └── SKILL.md         # 外掛 Skill 封裝，指向根目錄 SKILL.md
└── tests/
    ├── Test-Discover-AntigravitySession.ps1
    ├── Test-Invoke-AntigravityBridge.ps1
    ├── Test-E2E-Smoke.ps1               # 端對端整合測試
    └── test_antigravity_bridge_py.py
```

---

## 🧪 執行自動化測試

要執行完整的單元測試與端對端整合測試：

### PowerShell Pester 測試

```powershell
pwsh -Command "Invoke-Pester -Path ./tests"
```

### Python Pytest 測試套件

```bash
pytest tests/
```

---

## 📄 授權條款

本專案採用 [MIT License](LICENSE) 條款開源發布。
## 對話顯示與本機紀錄

預設的 Hub-native RPC 路徑會被 Antigravity 建立索引，預期至少出現在 `Outside of Project`；是否歸入特定 Project 仍由桌面程式決定。Antigravity 2.4.3 的 `agy` fallback 可能完全不可見，因為桌面 loader 尋找舊 `.pb` trajectory，而 CLI 寫入 SQLite `.db`。禁止為了強制顯示而注入或轉換 trajectory 檔案。

PowerShell wrapper 與 `agy` fallback 可追加本機 Markdown 紀錄。可用 `ANTIGRAVITY_BRIDGE_TRANSCRIPT_DIR` 指向專供 Codex 查閱的資料夾，PowerShell 亦可傳 `-TranscriptDirectory`；不想落地保存時可用 `-NoTranscript` / `--no-transcript`。
## 可靠傳遞與重試合約

auto 採可見性優先：先嘗試 Hub-native 環回 RPC，才可能使用 agy。Python 橋接把 prompt 視為傳遞操作，而不是可以任意重送的聊天訊息。

Python `prompt` 與 MCP `antigravity_prompt` 預設啟用安全 GUI auto-launch。只有在派發前確認沒有可用 session 且程序不存在／已死亡時才會開啟桌面程式；不會 kill/restart、不會對仍存活的 PID 開第二份，也不會在 `DELIVERY_UNKNOWN`、`INPUT_REQUIRED`、replay 或 Send 開始後觸發。啟動採跨 bridge process 單飛鎖，接著做有上限的重新 discovery/probe。CLI 可用 `--no-auto-launch`，MCP 可設 `auto_launch: false`；非預設安裝可用 `--gui-path`／`gui_path` 或 `ANTIGRAVITY_GUI_PATH`。明確指定 `agy` transport 不會啟動 GUI。

- 呼叫端應在第一次呼叫前產生 UUID request_id、保留回傳 receipt，並在每次重試沿用相同 key。若未提供，橋接只會替該次呼叫產生；不同呼叫各自產生的 ID 無法跨呼叫去重。
- 持久 SQLite request journal 預設位於 %LOCALAPPDATA%\AntigravityBridge\requests.sqlite3，僅記錄 fingerprint、傳遞狀態、cascade/marker ID 與 receipt；不保存 prompt 原文或 CSRF token。
- 同一 request_id 搭配不同請求內容會回傳 CONFLICT，不可當成重試。
- SendUserCascadeMessage 一旦開始，DELIVERY_UNKNOWN、IN_PROGRESS 與其他 pending／非終態結果必須用同一 key 對同一 cascade/marker 做 reconcile；不得 fallback 到 agy，也不得重新送 prompt。
- 單一 global deadline 涵蓋 RPC、reconcile 與符合條件的 agy fallback；期限耗盡即跳過 fallback。

mission_id 與 lane_id 是刻意 fan-out 的中繼資料。加上 owner 才啟用持久 lane 協調；既有 active lane 必須提供完全相符的 owner 與 epoch，所有協調拒絕都不可透過 agy fallback 繞過。

    python3 scripts/antigravity_bridge.py lane claim --mission-id review-2026-08-21 --lane-id security --owner-id reviewer-1 --quota 3
    python3 scripts/antigravity_bridge.py prompt --prompt "檢查 src/main.py" --workspace-path . --request-id "550e8400-e29b-41d4-a716-446655440000" --mission-id review-2026-08-21 --lane-id security --owner-id reviewer-1 --lane-epoch 1
    python3 scripts/antigravity_bridge.py health --no-probe

可用 `ANTIGRAVITY_ALLOWED_WORKSPACES`（依作業系統 path separator 分隔）強制 workspace allow-list。權限等待會回非終態 `INPUT_REQUIRED`；請在 Antigravity 核准後沿用同一 request ID reconcile。`DELIVERY_UNKNOWN`、`INPUT_REQUIRED` 與非 Bridge 所有的程序一律不得觸發重啟。

PowerShell 是相容／診斷層，沒有獨立持久 journal；需要冪等傳遞時請使用 Python CLI 或 MCP。

設計採用 [AWS idempotent API](https://docs.aws.amazon.com/ec2/latest/devguide/ec2-api-idempotency.html) client-token 原則。長時間 MCP 作業可回報 [progress](https://modelcontextprotocol.io/specification/latest/basic/patterns/progress) 或接收 [cancellation](https://modelcontextprotocol.io/specification/latest/basic/patterns/cancellation)；取消或逾時不代表傳遞必定未發生。
