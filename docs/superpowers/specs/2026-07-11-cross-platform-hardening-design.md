# Antigravity Bridge Codex 跨平台硬化設計

## 目標

讓 Antigravity Bridge Codex 在 Windows 與 macOS 上具備可重複安裝、可診斷失敗、可驗證同步與不污染工作區的完整行為，同時保留現有 bridge、plugin、personal skill 與 MCP 使用方式。

## 全域約束

- Windows 與 macOS 是正式支援平台；Linux discovery 維持 best-effort，不擴大本次驗收範圍。
- Windows PowerShell 5.1 只能作為啟動外殼；實際 PowerShell 腳本以 PowerShell 7.4 LTS 以上執行。
- 所有中文檔案與 CLI 輸出使用 UTF-8；repository 文字檔統一 LF。
- 安裝器不得安裝、升級、解除安裝或刪除任何 Python runtime。
- Windows 同時存在 Python 3.13.11、3.13.14、3.11.9 時必須安全共存。
- 變更必須最小化、保留既有功能，並以測試先行實作。

## 方案選擇

採用「安裝時解析並綁定已驗證的 Python 絕對路徑」方案，不使用動態 PATH 猜測作為正常路徑，也不固定要求單一 Python minor version。

未採用方案：

- 每次透過 `py -3` 動態啟動：執行結果會隨 Windows launcher 預設版本漂移。
- 固定 Python 3.11：bridge 只使用標準函式庫，沒有必要增加版本綁定與維護負擔。
- 隨 plugin 內附 Python runtime：套件體積、更新與安全責任明顯超出本專案範圍。

## Interpreter Resolution

### 共同行為

Personal skill、local marketplace plugin 與 stable MCP registration 必須使用同一次解析出的 interpreter。JSON manifest 的 `command` 保存未加引號的絕對路徑；路徑中的空白由 process argument API 處理。

解析成功必須同時滿足：

- 可取得絕對路徑。
- 路徑存在。
- 能成功執行 `-c "import sys; print(sys.executable)"`。
- Windows 上不得解析到 `Microsoft\WindowsApps\python*.exe` alias。

找不到有效 interpreter 時，安裝器必須停止並輸出平台對應的操作提示，不得把裸 `python` 或 `python3` 寫入 installed manifest 假裝完成。

### Python installer

解析順序：

1. `ANTIGRAVITY_PYTHON` 指定的 interpreter。
2. 當前 `sys.executable`。
3. Windows：`py -3` 回報的 `sys.executable`，再檢查 `python.exe`／`python3.exe` 候選。
4. macOS：經驗證的 `python3`，再檢查 `python`。

使用者以特定 Python 執行 `install.py` 時，當前 `sys.executable` 具有最高優先權。

### PowerShell installer

解析順序：

1. `ANTIGRAVITY_PYTHON`。
2. Windows：透過 `py -3 -c` 取得絕對 `sys.executable`。
3. 經 `Get-Command` 找到且能執行驗證命令的 `python`／`python3`。
4. macOS：優先驗證 `python3`，再驗證 `python`。

PowerShell resolver 必須獨立可測，並由 installed manifests 與 stable MCP registration 共用。

### Python runtime 保護

程式碼與文件必須明確保證：

- `python3` 在 macOS 文件中是平台指令，不代表老舊套件。
- Windows Store alias 只會被略過，不會被移除。
- 安裝器不執行 `pip uninstall`、Python uninstaller 或刪除 Python 安裝路徑。
- 多版本 Python fixture 的 sentinel 在安裝前後必須保持存在。

## 安裝、升級與內容一致性

Fresh install、repeat install 與 upgrade install 使用相同同步入口。

語意冪等條件：

- Personal skill 與 marketplace plugin 的受管理內容在重跑後等於 source。
- Installed `.mcp.json` 只允許 interpreter 絕對路徑不同。
- Plugin manifest 只允許安裝器產生的 cachebuster version 不同。
- Marketplace 與 stable MCP registration 不會累積重複項目。
- 過期或人為置入的 managed-file sentinel 會被最新版 source 覆蓋。
- Codex executable 不存在時仍完成檔案同步，並輸出「未註冊」警告。
- Codex CLI 註冊失敗時回報失敗，不宣稱完整安裝成功。

測試使用隔離 `CODEX_HOME` 與 fake Codex executable，不碰開發者實際設定。正式驗證全部通過後，才以實際 installer 更新本機 personal skill／marketplace plugin／stable MCP registration。

## Session Discovery 與 RPC 診斷

### Session discovery

Windows 與 macOS 必須測試：

- 預設 logs 存在。
- 所有候選 logs 不存在。
- 明確指定的 log path 不存在。
- 空檔、缺少 token、缺少 port。
- Windows CRLF 與 UTF-8 BOM。
- macOS live logs 與 rotated snapshot fallback。

錯誤訊息需指出下一步（啟動並登入 Antigravity），列出安全的 checked paths，且不得輸出 CSRF token。

### RPC

Python 與 PowerShell 都必須正規化：

- HTTP 200＋有效 JSON。
- HTTP 200＋空 body。
- HTTP 200＋malformed JSON。
- HTTP 200＋非物件 JSON。
- HTTP 500＋JSON body。
- HTTP 500＋純文字或 HTML body。
- Connection failure／timeout。

錯誤包含 RPC method、HTTP status 或連線類型，以及長度受限的安全 body 摘要。任何診斷都不得包含 CSRF token；原始 trajectory 仍只在明確要求時回傳。

## Capability Matrix Artifact Lifecycle

每次執行在 workspace 下建立 `.antigravity-matrix/<GUID>/`，所有 read、write、edit、web probes 只存在該次目錄。

- 預設在 `finally` 移除該 GUID 目錄。
- `-KeepArtifacts` 明確指定時保留，JSON 結果標示 `artifactsRetained: true`。
- Cleanup 只能移除本次建立的 GUID 目錄，不能刪除既有 `.antigravity-matrix` 內容或其他 workspace 檔案。
- 並行執行不得碰撞。
- Probe failure／timeout 應記錄為單項結果；能繼續的測試應繼續，最後仍輸出完整 JSON。
- Cleanup 自身失敗需進入診斷欄位，不得掩蓋原始測試結果。

## 行尾與跨平台 CI

新增 `.gitattributes`：

- `*.py`、`*.ps1`、`*.md`、`*.json`、`*.yaml`、`*.yml`、`*.svg` 使用 `text eol=lf`。
- PNG 等二進位資產使用 `-text`。
- 若未來新增 Windows batch 檔，明確指定 `eol=crlf`。

修正 PowerShell 測試內依賴反斜線的 `Join-Path`，確保在 macOS PowerShell 7 可執行。

CI matrix：

- Python：Windows／macOS × Python 3.11／3.13。
- PowerShell regression：Windows／macOS，PowerShell 7。
- 行尾檢查：拒絕受管理文字檔的 CRLF 或混合行尾。

Windows PowerShell 5.1 不執行核心測試；文件提供將命令轉交 PowerShell 7.4 LTS 的方式。

## 測試與手動 E2E

新增或擴充自動測試：

- Interpreter resolver：override、`sys.executable`、`py -3`、多版本、Store alias、無候選 fail-fast。
- Installer：fresh、repeat、stale upgrade、Codex absent、Codex present、registration failure、runtime sentinel 保留。
- Installed parity：source、personal skill、marketplace plugin 的 managed payload 一致。
- Session discovery：缺失、BOM／CRLF、snapshot fallback、redaction。
- RPC：valid／empty／malformed／HTTP 500／network error。
- Capability matrix：dry-run、成功 cleanup、exception cleanup、`-KeepArtifacts`、並行 GUID 隔離。
- Repository contract：`.gitattributes`、跨平台 CI matrix、平台化文件措辭。

新增 `tests/manual-e2e.md`，記錄 Windows 與 macOS 的：

- Clean install。
- Repeat／upgrade install。
- Codex executable 不存在。
- Antigravity session 不存在。
- Session 存在但 RPC 失敗。
- Gemini 回覆後 Codex 讀取結果。
- Windows 多 Python 並存。
- macOS `python3` installer。
- Installed parity。
- Probe cleanup 與 `-KeepArtifacts`。

## 文件

更新 README 與 `references/skill-packaging.md`：

- macOS：`python3 scripts/install.py`。
- Windows：`py -3.13 scripts/install.py`，或使用 PowerShell 7 執行 `scripts/install.ps1`。
- `python3` 明確標記為 macOS 指令，不是 Windows 待移除套件。
- Source `.mcp.json` 是安裝模板；installed copies 才是可執行設定。
- 無有效 interpreter 時的修復步驟。
- Python 多版本共存與「永不移除 runtime」政策。

## 完成條件

- 所有新增測試都經過 RED → GREEN。
- Python 與 PowerShell regression 在本機通過。
- macOS live discovery、RPC smoke 與 Gemini reply readback 通過。
- Capability matrix 預設執行後不留下 probe。
- 實際 macOS installed copies 與 source parity 通過。
- Windows CI 通過；Windows manual E2E 由使用者在目標機執行並記錄。
- `git diff --ignore-space-at-eol` 不再需要用來掩蓋 repository 行尾噪音。
