# Antigravity Bridge Codex 雙 AI 協作橋接套件

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![AI Integration](https://img.shields.io/badge/AI-Codex%20%2B%20Gemini-orange.svg)]()

**Antigravity Bridge Codex** 是一套開源的跨 AI 協作橋接 Skill 與 Plugin。它能讓 **Codex**（基於 GPT 的 CLI / IDE 助理）與本機正在執行的 **Antigravity**（基於 Gemini 的桌面應用程式）進行無縫雙向通訊與協同工作。

在協作架構中，Codex 擔任監督者（Supervisor）與稽核者（Reviewer），負責任務拆解與品質把關；同時將程式碼撰寫、大範圍修改、研究及創意發想委派給本機 Antigravity 的 Gemini 模型執行。

---

## 💡 核心特色

- **自動化 Session 偵測**：自動掃描系統日誌（Log），於 Windows、macOS 與 Linux/WSL 上自動提取 Antigravity 服務端口（Port）與 CSRF Token。
- **雙向 AI 協同工作流**：支援 Codex 建立 Cascade 任務區、發送提示詞、觀察軌跡（Trajectory）並接收 Gemini 的結構化回傳。
- **全平台與雙語言腳本支援**：原生支援 PowerShell 7+ 與 Python 3.8+，兼具效能與跨平台彈性。
- **模型動態對應與退回**：自動偵測 Antigravity 本機模型識別碼，並相容內部列舉佔位符（`MODEL_PLACEHOLDER_M*`）。
- **MCP Server 整合**：提供 Model Context Protocol (MCP) 伺服器設定（`.mcp.json`），方便支援 MCP 的開發環境直接呼叫。
- **本機環回與隱私安全**：所有通訊皆限制於本機環回網路（`127.0.0.1`），完全尊重開發者設定的本機工作區目錄權限。

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
             │     本機環回 RPC (127.0.0.1)     │
             └──────────────► ◄────────────────┘
```

---

## 🚀 快速開始與安裝

### 選項 1：PowerShell 安裝與使用 (Windows / macOS / Linux)

執行自動化安裝腳本：

```powershell
pwsh -ExecutionPolicy Bypass -File ./scripts/install.ps1
```

手動偵測本機 Session 並發送測試訊息：

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
python3 scripts/antigravity_bridge.py send --prompt "檢查 main.py 是否有程式漏洞" --workspace-path "."
```

---

## 📂 專案目錄結構

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

本專案採用 [Apache 2.0 License](LICENSE) 條款開源發布。
