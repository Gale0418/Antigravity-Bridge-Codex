# Cross-Platform Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 Antigravity Bridge Codex 在 Windows 與 macOS 上能以已驗證的 Python 安全安裝、重跑與升級，提供不洩漏祕密的 session/RPC 診斷，隔離 capability probe 產物，並由跨平台 CI、文件與實機 smoke 驗證保護。

**Architecture:** Python installer 與 PowerShell installer 各自暴露可注入依賴的 interpreter resolver，解析出的絕對路徑同時寫入 skill/plugin manifest 與 stable MCP registration。Bridge discovery/RPC 將所有負面結果轉成含 method/status、checked paths 與長度限制 body 摘要的安全錯誤；capability matrix 以每次執行的 GUID artifact root 管理生命週期。測試以隔離 CODEX_HOME、fake Codex、fake logs/RPC server 與 PowerShell standalone assertion scripts 驗證行為，最後才做 macOS 實機安裝與 live readback。

**Tech Stack:** Python 3.11/3.13 `unittest`、PowerShell 7 standalone assertion scripts、Python 標準函式庫 `subprocess`/`urllib`/`tempfile`、GitHub Actions、Markdown 文件。

## Global Constraints

- Windows 與 macOS 是正式支援平台；Linux discovery 維持 best-effort，不擴大本次驗收範圍。
- Windows PowerShell 5.1 只能作為啟動外殼；實際 PowerShell 腳本以 PowerShell 7.4 LTS 以上執行。
- 所有中文檔案與 CLI 輸出使用 UTF-8；repository 文字檔統一 LF。
- 安裝器不得安裝、升級、解除安裝或刪除任何 Python runtime。
- Windows 同時存在 Python 3.13.11、3.13.14、3.11.9 時必須安全共存。
- 變更必須最小化、保留既有功能，並以測試先行實作。
- 任何失敗診斷不得輸出 CSRF token；原始 trajectory 只在明確要求時回傳。
- 每一項任務都必須先 RED、再 GREEN，獨立驗證後建立一個小型 commit。

## File Map

- Modify `scripts/install.py`: 可測試的 Python interpreter resolver、manifest 同步與註冊錯誤邊界。
- Modify `scripts/install.ps1`: PowerShell 7 resolver、跨平台 `Join-Path` 與同等安裝語意。
- Modify `scripts/antigravity_bridge.py`: session/RPC 安全診斷與 response shape 驗證。
- Modify `scripts/Discover-AntigravitySession.ps1`: BOM/CRLF 讀取與 checked-path/redaction 訊息。
- Modify `scripts/Invoke-AntigravityRpc.ps1`: HTTP/JSON/network 負面結果正規化。
- Modify `scripts/Run-AntigravityCapabilityMatrix.ps1`: `.antigravity-matrix/<GUID>` artifact root、`finally` cleanup 與 `-KeepArtifacts`。
- Modify `tests/test_antigravity_bridge_py.py`: Python resolver、installer parity、session/RPC 負面案例。
- Modify `tests/Test-*.ps1`: 可直接以 `pwsh -NoLogo -NoProfile -File` 執行的 resolver、installer、session/RPC、matrix 與 repository contract assertion scripts。
- Create `tests/manual-e2e.md`: Windows/macOS 清裝、重跑、升級、session/RPC、parity 與 cleanup 記錄表。
- Create `.gitattributes`: 受管理文字檔 LF 與二進位 `-text` 規則。
- Modify `.github/workflows/pester.yml`: Windows/macOS × Python 3.11/3.13、PowerShell 7 與行尾檢查 matrix。
- Modify `README.md`, `README.zh-TW.md`, `references/skill-packaging.md`: 平台指令、interpreter 修復、runtime 永不移除與 source/installed manifest 說明。

---

### Task 1: 建立可注入的 Python 與 PowerShell interpreter resolver

**Files:**
- Modify: `scripts/install.py`（取代 `resolve_mcp_python_command` 並新增 `verify_interpreter`、`resolve_interpreter`）。
- Modify: `scripts/install.ps1`（取代 `Resolve-McpPythonCommand` 並新增 `Test-PythonInterpreter`、`Resolve-PythonInterpreter`）。
- Modify: `tests/test_antigravity_bridge_py.py`（新增 resolver 單元測試）。
- Modify: `tests/Test-SkillPackaging.ps1`（新增可直接執行的 PowerShell resolver assertion）。

**Interfaces:**
- `scripts/install.py`: `verify_interpreter(candidate: str | os.PathLike[str], runner: Callable[..., CompletedProcess] = subprocess.run) -> str` 回傳存在且 `-c "import sys; print(sys.executable)"` 成功的絕對路徑；`resolve_interpreter(*, environment_value: str | None = None, current_executable: str | None = None, platform_name: str | None = None, which: Callable[[str], str | None] = shutil.which, runner: Callable[..., CompletedProcess] = subprocess.run) -> str` 依規格順序解析，無候選時拋出含平台修復步驟的 `RuntimeError`。
- `scripts/install.ps1`: `Test-PythonInterpreter -Candidate [string] -NativeInvoker [scriptblock]` 回傳驗證後絕對路徑或 `$null`；`Resolve-PythonInterpreter -EnvironmentValue [string] -CurrentExecutable [string] -Platform [string] -CommandResolver [scriptblock] -NativeInvoker [scriptblock]` 回傳同一絕對路徑，並拒絕 Windows Store alias。
- 兩個 installer 的 manifest normalizer 與 `Register-StableMcpServer` 只能呼叫 resolver，不得再寫入裸 `python`/`python3`。

- [ ] **Step 1: Write the failing tests (RED)**

```python
def test_resolver_prefers_override_and_rejects_store_alias(self):
    installer = load_installer_module()
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=command[0] + "\\n")
    self.assertEqual(
        installer.resolve_interpreter(
            environment_value="/opt/Python 3.13/bin/python3",
            current_executable="/tmp/current-python",
            platform_name="macOS",
            which=lambda _: None,
            runner=runner,
        ),
        str(Path("/opt/Python 3.13/bin/python3").resolve()),
    )
    self.assertEqual(calls[0][0], "/opt/Python 3.13/bin/python3")

def test_resolver_fails_with_platform_repair_message(self):
    installer = load_installer_module()
    with self.assertRaisesRegex(RuntimeError, "Windows.*Python 3.11.*3.13"):
        installer.resolve_interpreter(platform_name="Windows", which=lambda _: None, runner=lambda *a, **k: (_ for _ in ()).throw(OSError()))
```

```powershell
$result = Resolve-PythonInterpreter -EnvironmentValue 'C:\Python 3.13\python.exe' -Platform 'Windows' `
    -CommandResolver { param($name) $null } -NativeInvoker { param($path) [pscustomobject]@{ ExitCode = 0; StdOut = "$path`n" } }
if ($result -ne [System.IO.Path]::GetFullPath('C:\Python 3.13\python.exe')) {
    throw "ANTIGRAVITY_PYTHON override resolved incorrectly: '$result'"
}

try {
    Resolve-PythonInterpreter -EnvironmentValue '' -CurrentExecutable '' -Platform 'Windows' `
        -CommandResolver { param($name) $null } -NativeInvoker { throw 'not found' } | Out-Null
    throw 'Expected Resolve-PythonInterpreter to fail without a valid candidate.'
} catch {
    if ($_.Exception.Message -notmatch 'Python 3\.11.*3\.13') {
        throw "Unexpected resolver failure: $($_.Exception.Message)"
    }
}
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `python -m unittest tests.test_antigravity_bridge_py -k resolver -v`; `pwsh -NoLogo -NoProfile -File tests/Test-SkillPackaging.ps1`.

Expected: Python reports missing `resolve_interpreter`; the standalone PowerShell script throws for missing `Resolve-PythonInterpreter`.

- [ ] **Step 3: Write minimal implementation**

Implement candidate order exactly as `ANTIGRAVITY_PYTHON`, current `sys.executable`, Windows `py -3`, then platform command candidates. For every candidate, call `verify_interpreter`, reject `Microsoft\WindowsApps\python*.exe`, normalize `sys.executable` output, and raise a platform-specific repair message. Update Python `normalize_mcp_manifest` and both registration paths to use the returned path. In PowerShell, use `Get-Command` only through the injected resolver, invoke `-c 'import sys; print(sys.executable)'`, and use `Join-Path` for all paths.

- [ ] **Step 4: Run tests to verify they pass (GREEN)**

Run: `python -m unittest tests.test_antigravity_bridge_py -k resolver -v`; `pwsh -NoLogo -NoProfile -File tests/Test-SkillPackaging.ps1`.

Expected: all resolver cases PASS; no manifest contains a bare interpreter command.

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py scripts/install.ps1 tests/test_antigravity_bridge_py.py tests/Test-SkillPackaging.ps1
git commit -m "feat: resolve and validate cross-platform Python interpreters"
```

### Task 2: 使安裝、重跑、升級與 parity 可驗證且絕不刪除 Python

**Files:**
- Modify: `scripts/install.py`（抽出同步入口、registration failure 邊界與 runtime 保護）。
- Modify: `scripts/install.ps1`（對齊 Python installer 的 fresh/repeat/upgrade 行為與 failure status）。
- Modify: `tests/test_antigravity_bridge_py.py`（隔離 CODEX_HOME、fake Codex、stale sentinel、多版本 runtime fixture）。
- Modify: `tests/Test-SkillPackaging.ps1`（PowerShell installer parity 與 registration failure）。

**Interfaces:**
- Python `sync_install(source_root: Path, codex_home: Path, codex_executable: Path | None) -> InstallReport` 與 PowerShell `Sync-Install -SourceRoot [string] -CodexHome [string] -CodexExecutable [string] -> [pscustomobject]` 對應輸出欄位 `Synced`, `Registered`, `Warnings`；兩者 fresh/repeat/upgrade 皆使用同一同步流程。
- `InstallReport`/PS custom object 必須標示 `codexFound`, `registrationAttempted`, `registrationSucceeded`，Codex 缺失時同步成功但回報未註冊警告，Codex CLI 非零時以失敗結束且不宣稱完整成功。

- [ ] **Step 1: Write the failing tests (RED)**

```python
def test_repeat_upgrade_overwrites_managed_skill_and_preserves_python_runtimes(self):
    installer = load_installer_module(); home = fresh_test_dir("installer-lifecycle")
    source_root = Path(__file__).resolve().parents[1]
    source_skill = source_root / "SKILL.md"
    runtimes = [home / "Python311" / "python.exe", home / "Python313-a" / "python.exe", home / "Python313-b" / "python.exe"]
    for runtime in runtimes:
        runtime.parent.mkdir(parents=True); runtime.write_text("sentinel", encoding="utf-8")
    with patch.object(installer, "get_codex_executable", return_value=None):
        first = installer.sync_install(source_root, home, None)
        self.assertFalse(first.codexFound)
        skill = home / "skills" / "antigravity-bridge-codex"
        (skill / "SKILL.md").write_text("stale", encoding="utf-8")
        second = installer.sync_install(source_root, home, None)
        self.assertFalse(second.codexFound)
    self.assertEqual((skill / "SKILL.md").read_text(encoding="utf-8"), source_skill.read_text(encoding="utf-8"))
    self.assertTrue(all(runtime.exists() for runtime in runtimes))
```

```powershell
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$codexHome = Join-Path ([System.IO.Path]::GetTempPath()) "installer-lifecycle-$([guid]::NewGuid().Guid)"
$null = New-Item -ItemType Directory -Force -Path $codexHome
foreach ($name in @('Python311', 'Python313-a', 'Python313-b')) {
    $runtime = Join-Path $codexHome "$name/python.exe"
    $null = New-Item -ItemType Directory -Force -Path (Split-Path $runtime)
    Set-Content -LiteralPath $runtime -Value 'sentinel' -NoNewline
}
$first = Sync-Install -SourceRoot $sourceRoot -CodexHome $codexHome -CodexExecutable ''
$installedSkill = Join-Path $codexHome 'skills/antigravity-bridge-codex/SKILL.md'
Set-Content -LiteralPath $installedSkill -Value 'stale' -NoNewline
$second = Sync-Install -SourceRoot $sourceRoot -CodexHome $codexHome -CodexExecutable ''
$sourceText = Get-Content -LiteralPath (Join-Path $sourceRoot 'SKILL.md') -Raw
$installedText = Get-Content -LiteralPath $installedSkill -Raw
if ($installedText -ne $sourceText) { throw 'Repeat install did not restore managed SKILL.md from source.' }
if ((Get-ChildItem -LiteralPath $codexHome -Recurse -File | Where-Object Name -eq 'python.exe').Count -ne 3) {
    throw 'Installer modified or removed a Python runtime sentinel.'
}
$manifest = Get-Content -LiteralPath (Join-Path $codexHome 'skills/antigravity-bridge-codex/.mcp.json') -Raw | ConvertFrom-Json
if ($manifest.mcpServers.'antigravity-bridge-codex'.command -notmatch '^[A-Za-z]:|^/') {
    throw 'Installed MCP command is not an absolute interpreter path.'
}
Write-Host 'PASS: repeat install overwrites managed files and preserves runtimes'
```
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `python -m unittest tests.test_antigravity_bridge_py -k lifecycle -v`; `pwsh -NoLogo -NoProfile -File tests/Test-SkillPackaging.ps1`.

Expected: lifecycle test exposes missing report/idempotency contract or incorrect registration status.

- [ ] **Step 3: Write minimal implementation**

讓 managed copy 使用單一 `copy_fresh_item`/`Copy-FreshItem` 入口，僅刪除 skill/plugin 目標，不掃描或刪除任何 runtime 路徑；marketplace 與 MCP registration 先 remove 再 add，確保不累積重複。將 registration exception 轉成明確非零結果，Codex 不存在則只警告。以 JSON manifest comparison 忽略 resolver 絕對路徑與 cachebuster version，並在測試 fixture 內用 fake executable 記錄呼叫。

- [ ] **Step 4: Run tests to verify they pass (GREEN)**

Run: `python -m unittest tests.test_antigravity_bridge_py -v`; `pwsh -NoLogo -NoProfile -File tests/Test-SkillPackaging.ps1`。

Expected: fresh/repeat/stale-upgrade、Codex absent/present/registration failure、source/installed parity 與所有 runtime sentinel 案例 PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py scripts/install.ps1 tests/test_antigravity_bridge_py.py tests/Test-SkillPackaging.ps1
git commit -m "feat: make installer lifecycle idempotent and runtime-safe"
```

### Task 3: 強化 Windows/macOS session discovery 與安全負面診斷

**Files:**
- Modify: `scripts/antigravity_bridge.py`（`resolve_log_path`、`session_from_text`、`get_session_info`）。
- Modify: `scripts/Discover-AntigravitySession.ps1`（對應函式與 UTF-8 讀取）。
- Modify: `tests/test_antigravity_bridge_py.py`（空檔、token/port 缺失、BOM/CRLF、候選不存在、macOS rotated fallback）。
- Modify: `tests/Test-Discover-AntigravitySession.ps1`（同等 standalone diagnostics assertions）。

**Interfaces:**
- Python `safe_diagnostic(message: str, *, checked_paths: Iterable[str] = (), secret_values: Iterable[str] = (), max_body: int = 240) -> str` 必須 redaction、列出 checked paths 與下一步「請啟動並登入 Antigravity」；`session_from_text` 與 `get_session_info` 的 `RuntimeError` 只使用此診斷。
- PowerShell `New-AntigravityDiagnostic` 與 `Get-AntigravitySessionInfoFromText`/`Resolve-AntigravityLogPath` 產生同語意訊息；`ConvertTo-AntigravitySessionPublicInfo` 預設只回傳 `<redacted>`。

- [ ] **Step 1: Write the failing tests (RED)**

```python
def test_missing_session_diagnostic_lists_paths_and_next_step_without_token(self):
    with self.assertRaisesRegex(RuntimeError, "Checked:.*啟動並登入 Antigravity") as raised:
        bridge.get_session_info(platform_name="Windows", home_directory="/missing", appdata_directory="/missing")
    self.assertNotIn("11111111-2222-3333-4444-555555555555", str(raised.exception))

def test_bom_crlf_and_rotated_snapshot_are_read(self):
    home = fresh_test_dir("session-snapshot"); snapshot = home / "Library/Application Support/Antigravity/logs/20260711"
    snapshot.mkdir(parents=True)
    (snapshot / "main.log").write_bytes(b"\\xef\\xbb\\xbfargv --csrf_token 11111111-2222-3333-4444-555555555555\\r\\nLocal: https://127.0.0.1:1/\\r\\n")
    (snapshot / "ls-main.1.log").write_bytes(b"process with pid 9\\r\\nport at 1 for HTTPS\\r\\nport at 2 for HTTP\\r\\n")
    session = bridge.get_session_info(platform_name="macOS", home_directory=home)
    self.assertEqual(session.http_port, 2)
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `python -m unittest tests.test_antigravity_bridge_py -k session -v`; `pwsh -NoLogo -NoProfile -File tests/Test-Discover-AntigravitySession.ps1`。

Expected: current errors omit next-step/checked-path safety or fail BOM/rotated fixture.

- [ ] **Step 3: Write minimal implementation**

用 `encoding='utf-8-sig'`（Python）與明確 `UTF8Encoding`/`ReadAllText`（PowerShell）讀取 BOM/CRLF；保留 Windows 預設、macOS live、snapshot `ls-main.log` 與 `ls-main.*.log` 候選順序。錯誤只包含檔案路徑與缺少欄位，CSRF 僅存於 session 物件；所有 public output 預設 redacted。

- [ ] **Step 4: Run tests to verify they pass (GREEN)**

Run: `python -m unittest tests.test_antigravity_bridge_py -k session -v`; `pwsh -NoLogo -NoProfile -File tests/Test-Discover-AntigravitySession.ps1`。

Expected: 預設 logs 存在/不存在、明確 path 不存在、空檔、token/port 缺失、BOM/CRLF、snapshot fallback 與 redaction 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/antigravity_bridge.py scripts/Discover-AntigravitySession.ps1 tests/test_antigravity_bridge_py.py tests/Test-Discover-AntigravitySession.ps1
git commit -m "fix: provide safe cross-platform session diagnostics"
```

### Task 4: 正規化 Python/PowerShell RPC 負面結果

**Files:**
- Modify: `scripts/antigravity_bridge.py`（`invoke_rpc` 與診斷 helper）。
- Modify: `scripts/Invoke-AntigravityRpc.ps1`（`Invoke-AntigravityRpc`/HTTP body parser）。
- Modify: `tests/test_antigravity_bridge_py.py`（mock `urlopen` 的 HTTP/JSON/network cases）。
- Modify: `tests/Test-Invoke-AntigravityRpc.ps1`（注入 fake web responses 的 standalone assertions）。

**Interfaces:**
- Python `invoke_rpc(method: str, body: dict[str, Any], session: AntigravitySession | None = None, opener: Callable[..., Any] = urllib.request.urlopen) -> dict[str, Any]`：200 空 body 回 `{}`；200 JSON 必須是 object，否則 `RuntimeError`；500/connection/timeout 訊息包含 method、status/type 與最多 240 字安全摘要。
- PowerShell `Invoke-AntigravityRpc -Method -Body -Session -RequestInvoker` 回傳 object；`ConvertTo-AntigravityRpcError` 負責截斷、HTML/純文字摘要與 CSRF redaction。

- [ ] **Step 1: Write the failing tests (RED)**

```python
@patch.object(bridge.urllib.request, "urlopen")
def test_rpc_diagnostics_cover_empty_malformed_non_object_http500_and_network(self, urlopen):
    session = bridge.AntigravitySession("SECRET-TOKEN", "https://127.0.0.1:1/", 1, 2, 3, "m", "l")
    for payload in (b"", b"{bad", b"[1]"):
        urlopen.return_value.__enter__.return_value.read.return_value = payload
        if payload == b"": self.assertEqual(bridge.invoke_rpc("Ping", {}, session), {})
        else:
            with self.assertRaisesRegex(RuntimeError, "Ping"): bridge.invoke_rpc("Ping", {}, session)
    error = urllib.error.HTTPError("u", 500, "", {}, io.BytesIO(b"SECRET-TOKEN html"))
    urlopen.side_effect = error
    with self.assertRaisesRegex(RuntimeError, "HTTP 500") as raised: bridge.invoke_rpc("Ping", {}, session)
    self.assertNotIn("SECRET-TOKEN", str(raised.exception))
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `python -m unittest tests.test_antigravity_bridge_py -k rpc -v`; `pwsh -NoLogo -NoProfile -File tests/Test-Invoke-AntigravityRpc.ps1`。

Expected: malformed/non-object JSON currently escapes as raw decoder errors and HTTP body may leak token.

- [ ] **Step 3: Write minimal implementation**

集中處理 response bytes：先截斷並遮罩 session token，再依 HTTP status 解析 JSON object；空 body 回空物件；malformed、array/scalar、500 JSON/HTML、`URLError` 與 timeout 皆拋出同格式 `Antigravity RPC <method> failed (<status/type>): <summary>`。PowerShell 使用 `Invoke-WebRequest`/注入 invoker，保留 method/status/type 欄位且不回傳 trajectory。

- [ ] **Step 4: Run tests to verify they pass (GREEN)**

Run: `python -m unittest tests.test_antigravity_bridge_py -k rpc -v`; `pwsh -NoLogo -NoProfile -File tests/Test-Invoke-AntigravityRpc.ps1`。

Expected: valid object、empty、malformed、non-object、HTTP 500 JSON/text/HTML、connection failure/timeout 及 token redaction 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/antigravity_bridge.py scripts/Invoke-AntigravityRpc.ps1 tests/test_antigravity_bridge_py.py tests/Test-Invoke-AntigravityRpc.ps1
git commit -m "fix: normalize RPC errors without leaking secrets"
```

### Task 5: 隔離 capability matrix artifact 並保證 cleanup

**Files:**
- Modify: `scripts/Run-AntigravityCapabilityMatrix.ps1`（新增 `[switch]$KeepArtifacts` 與 GUID lifecycle）。
- Modify: `tests/Test-Run-AntigravityCapabilityMatrix.ps1`（dry-run、成功/例外 cleanup、保留與並行隔離）。

**Interfaces:**
- `New-MatrixArtifactRoot -WorkspacePath [string] -Guid [guid] -> string` 回傳並建立 `<workspace>/.antigravity-matrix/<guid>/`；所有 read/write/edit/web probe path 必須由 `Join-Path $artifactRoot` 產生。
- script 輸出增加 `artifactRoot`, `artifactsRetained`, `cleanupError`；預設 `finally` 移除本次 GUID 目錄，`-KeepArtifacts` 保留並令 `artifactsRetained = $true`；單項 probe failure/timeout 只記錄 result，cleanup 失敗不覆蓋原始 results。

- [ ] **Step 1: Write the failing tests (RED)**

```powershell
$json = & $script -WorkspacePath $workspace -DryRun | ConvertFrom-Json
if ($json.artifactRoot -notmatch '\.antigravity-matrix[\\/][0-9a-f-]{36}$') { throw "Unexpected artifact root: $($json.artifactRoot)" }
if (Test-Path -LiteralPath $json.artifactRoot) { throw 'Dry-run cleanup left the artifact root behind.' }
if ($json.artifactsRetained) { throw 'Default dry-run must report artifactsRetained=false.' }

$kept = & $script -WorkspacePath $workspace -DryRun -KeepArtifacts | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $kept.artifactRoot)) { throw 'KeepArtifacts did not preserve its own artifact root.' }
if (-not $kept.artifactsRetained) { throw 'KeepArtifacts must report artifactsRetained=true.' }
Remove-Item -LiteralPath $kept.artifactRoot -Recurse -Force
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `pwsh -NoLogo -NoProfile -File tests/Test-Run-AntigravityCapabilityMatrix.ps1`。

Expected: current script writes timestamped files directly in workspace and does not accept `-KeepArtifacts`.

- [ ] **Step 3: Write minimal implementation**

在解析 workspace 後建立 GUID root，將所有 probe path 改成 root 子路徑；以 `$results`、`$cleanupError`、`$artifactsRetained` 變數包住完整流程，`try/finally` 只刪除本次 root。dry-run 也建立/清理 root 並輸出完整 JSON；`-KeepArtifacts` 跳過刪除。每個 RPC/probe 用 try/catch 追加 fail/timeout result 後繼續。

- [ ] **Step 4: Run tests to verify they pass (GREEN)**

Run: `pwsh -NoLogo -NoProfile -File tests/Test-Run-AntigravityCapabilityMatrix.ps1`。

Expected: dry-run、成功 cleanup、exception cleanup、KeepArtifacts、並行 GUID 隔離與 cleanupError 欄位 PASS；workspace 既有內容不受影響。

- [ ] **Step 5: Commit**

```bash
git add scripts/Run-AntigravityCapabilityMatrix.ps1 tests/Test-Run-AntigravityCapabilityMatrix.ps1
git commit -m "fix: isolate capability matrix artifacts by run"
```

### Task 6: 加入行尾契約與 Windows/macOS CI matrix

**Files:**
- Create: `.gitattributes`。
- Modify: `.github/workflows/pester.yml`。
- Modify: `tests/Test-RepositoryContract.ps1`（LF、matrix、PowerShell 7.4 啟動提示檢查）。
- Modify: all touched `*.py`, `*.ps1`, `*.md`, `*.json`, `*.yaml`, `*.yml`, `*.svg` only when normalizing EOL; do not alter semantic content.

**Interfaces:**
- `.gitattributes` must contain `*.py *.ps1 *.md *.json *.yaml *.yml *.svg text eol=lf`, binary `*.png -text`, and future `*.bat text eol=crlf` rules.
- Workflow jobs: Python matrix `windows-latest`/`macos-latest` × `3.11`/`3.13`; PowerShell regression on both OS with `pwsh`; `eol` job rejects CRLF/mixed endings in managed text.

- [ ] **Step 1: Write the failing tests (RED)**

```powershell
$attrs = Get-Content (Join-Path $repoRoot '.gitattributes') -Raw
foreach ($pattern in @('\*\.py.*text.*eol=lf', '\*\.png.*-text', '\*\.bat.*eol=crlf')) {
    if ($attrs -notmatch $pattern) { throw "Missing .gitattributes rule: $pattern" }
}
$workflow = Get-Content (Join-Path $repoRoot '.github/workflows/pester.yml') -Raw
foreach ($pattern in @('3\.11', '3\.13', 'windows-latest', 'macos-latest', 'pwsh')) {
    if ($workflow -notmatch $pattern) { throw "Workflow is missing required matrix value: $pattern" }
}
Write-Host 'PASS: attributes and cross-platform workflow contract'
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `pwsh -NoLogo -NoProfile -File tests/Test-RepositoryContract.ps1`。

Expected: `.gitattributes` is absent and workflow has no Python-version or PowerShell OS matrix.

- [ ] **Step 3: Write minimal implementation**

新增 attributes；workflow 使用 `actions/setup-python@v5` 與 `${{ matrix.python-version }}`，PowerShell job matrix 兩 OS 並明確 `shell: pwsh`；eol job 以 `git ls-files`/Python 檢查管理文字檔不得含 CRLF 或混合行尾。將 PowerShell 測試中的反斜線字串替換為 `Join-Path` 組合。

- [ ] **Step 4: Run tests to verify they pass (GREEN)**

Run: `pwsh -NoLogo -NoProfile -File tests/Test-RepositoryContract.ps1`; `git diff --check`; `python - <<'PY'` 逐一檢查 managed text bytes 不含 `\r\n`。

Expected: repository contract、行尾檢查與 YAML matrix assertions PASS。

- [ ] **Step 5: Commit**

```bash
git add .gitattributes .github/workflows/pester.yml tests/Test-RepositoryContract.ps1 scripts/install.py scripts/install.ps1 scripts/antigravity_bridge.py scripts/Discover-AntigravitySession.ps1 scripts/Invoke-AntigravityRpc.ps1 scripts/Run-AntigravityCapabilityMatrix.ps1 tests/test_antigravity_bridge_py.py tests/Test-SkillPackaging.ps1 tests/Test-Discover-AntigravitySession.ps1 tests/Test-Invoke-AntigravityRpc.ps1 tests/Test-Run-AntigravityCapabilityMatrix.ps1
git commit -m "ci: enforce cross-platform matrices and LF endings"
```

EOL normalization gate: 先以 `git diff --name-only -- . ':(glob)*.py' ':(glob)*.ps1' ':(glob)*.md' ':(glob)*.json' ':(glob)*.yaml' ':(glob)*.yml' ':(glob)*.svg'` 確認上述精確檔案清單，再以 `git diff --check` 與 Python bytes 掃描確認沒有 CRLF 或混合行尾；只有通過 gate 的檔案才能納入這個 commit，不得使用 `git add scripts tests` 等目錄型廣泛加入。

### Task 7: 補齊平台文件與 manual E2E runbook

**Files:**
- Create: `tests/manual-e2e.md`。
- Modify: `README.md`。
- Modify: `README.zh-TW.md`。
- Modify: `references/skill-packaging.md`。
- Modify: `tests/Test-RepositoryContract.ps1`（文件詞彙契約）。

**Interfaces:**
- 文件必須精確提供 `python3 scripts/install.py`（macOS）、`py -3.13 scripts/install.py`（Windows）與 `pwsh -NoLogo -NoProfile -File scripts/install.ps1`；說明 PowerShell 5.1 僅轉交給 7.4 LTS、source `.mcp.json` 是模板、installed copy 才可執行、無 interpreter 修復、Python 多版本共存與永不移除 runtime。
- `tests/manual-e2e.md` 每個案例包含前置條件、命令、預期 JSON/檔案結果、實際執行日期與操作者欄位，涵蓋 clean/repeat/upgrade、Codex absent、session absent、RPC failure、Gemini→Codex readback、Windows 多 Python、macOS installer、installed parity、cleanup/KeepArtifacts。

- [ ] **Step 1: Write the failing tests (RED)**

```powershell
$docs = (Get-Content (Join-Path $repoRoot 'README.md') -Raw) + (Get-Content (Join-Path $repoRoot 'README.zh-TW.md') -Raw) + (Get-Content (Join-Path $repoRoot 'references/skill-packaging.md') -Raw)
foreach ($pattern in @('python3 scripts/install\.py', 'py -3\.13 scripts/install\.py', 'never|永不|不得.*Python', 'source.*\.mcp\.json|installed.*\.mcp\.json')) {
    if ($docs -notmatch $pattern) { throw "Documentation contract missing: $pattern" }
}
$runbook = Get-Content (Join-Path $repoRoot 'tests/manual-e2e.md') -Raw
foreach ($term in @('Clean install','Repeat','upgrade','Codex executable','session','RPC','readback','Python 3.11','Python 3.13','KeepArtifacts','parity')) {
    if ($runbook -notmatch [Regex]::Escape($term)) { throw "Manual E2E runbook is missing: $term" }
}
Write-Host 'PASS: platform documentation and manual E2E contract'
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `pwsh -NoLogo -NoProfile -File tests/Test-RepositoryContract.ps1`。

Expected: required command/policy/runbook assertions fail before documentation changes.

- [ ] **Step 3: Write minimal implementation**

以繁體中文同步 README 與 packaging reference，明確把 `python3` 限定為 macOS 平台指令；加入無有效 interpreter 時的修復步驟、Windows Store alias 只略過不移除、安裝器不執行 pip/uninstaller/刪除 runtime。建立 manual E2E 表格，所有 shell 命令標示平台與 PowerShell 7.4 入口，並留出結果、日期、log path（不含 token）的填寫欄位。

- [ ] **Step 4: Run tests to verify they pass (GREEN)**

Run: `pwsh -NoLogo -NoProfile -File tests/Test-RepositoryContract.ps1`; `rg -n 'python3 scripts/install\.py|py -3\.13 scripts/install\.py|KeepArtifacts|readback' README.md README.zh-TW.md references tests/manual-e2e.md`。

Expected: 文件契約與 manual scenario coverage PASS，沒有把 `python3` 描述成 Windows 待移除套件。

- [ ] **Step 5: Commit**

```bash
git add README.md README.zh-TW.md references/skill-packaging.md tests/manual-e2e.md tests/Test-RepositoryContract.ps1
git commit -m "docs: document safe platform installs and manual e2e"
```

### Task 8: 完成 macOS 實機 reinstall、parity 與 live smoke gate

**Files:**
- Modify: `tests/manual-e2e.md`（填入實際 macOS 結果與 redacted 證據）。

**Interfaces:**
- 實機驗證只使用目前 checkout 的 `scripts/install.py`、隔離 `CODEX_HOME` 做 dry run，再以使用者指定的實際 `CODEX_HOME` 做一次 macOS reinstall；實際 macOS reinstall 會修改使用者安裝內容，列為**需使用者明確授權**的驗證步驟，且不得移除或修改 Python runtime。
- 驗證輸出需包含 source/installed managed payload parity、manifest interpreter 絕對路徑、stable MCP registration、capability matrix cleanup、live discovery/RPC smoke 與 Gemini 回覆後 Codex readback；CSRF token 一律 `<redacted>`。

- [ ] **Step 1: Write the failing gate checklist (RED)**

```bash
test "$(uname -s)" = "Darwin"
python3 -m unittest discover -s tests -p 'test_*.py'
pwsh -NoLogo -NoProfile -File tests/Test-RepositoryContract.ps1
```

Expected before implementation completion: at least one parity, cleanup or live smoke assertion is not yet recorded as PASS in `tests/manual-e2e.md`。

- [ ] **Step 2: Run the gate to verify it is incomplete (RED)**

Run the commands above plus `python3 scripts/install.py` with isolated `CODEX_HOME`; capture only exit codes, paths and redacted JSON。

- [ ] **Step 3: Execute the minimal real-world verification**

1. `export CODEX_HOME="$(mktemp -d)"; python3 scripts/install.py`；再次執行確認 repeat/upgrade parity，放置 stale managed sentinel 後再執行確認被 source 覆蓋。
2. **需使用者授權後才可執行真實 macOS reinstall：** `read -r "確認要更新實際 CODEX_HOME？輸入 YES: " approval; test "$approval" = YES && python3 scripts/install.py`。若未獲授權，只記錄隔離 dry run 結果，不得宣稱實機 reinstall PASS。
3. 比對 source、`$CODEX_HOME/skills/antigravity-bridge-codex` 與 local marketplace plugin 的 managed files；只允許 interpreter 絕對路徑與 cachebuster version 差異。
4. 在已登入 Antigravity 的 macOS session 執行 `python3 scripts/antigravity_bridge.py discover`、`smoke --prompt 'Please reply only BRIDGE_OK' --pattern BRIDGE_OK`，再以 Codex 讀取回覆結果；session/RPC failure 另以隔離 fake log/server 驗證診斷。
5. 執行 `pwsh -NoLogo -NoProfile -File scripts/Run-AntigravityCapabilityMatrix.ps1 -DryRun` 與 `-KeepArtifacts`，確認預設無 GUID 殘留、保留模式只留自己的 root。
6. 將日期、OS、Python/PowerShell 版本、命令、結果與 redacted evidence 填入 runbook；若 live session 不可用，記錄阻礙與已通過的隔離測試，不偽造 PASS。

- [ ] **Step 4: Run tests to verify they pass (GREEN)**

Run: `python3 -m unittest discover -s tests -p 'test_*.py'`; `pwsh -NoLogo -NoProfile -File tests/Test-RepositoryContract.ps1`; `git diff --check`; compare the recorded parity hashes and cleanup assertions in `tests/manual-e2e.md`。

Expected: Python/PowerShell regression、macOS installed parity、live discovery/RPC/readback、matrix cleanup 與行尾 gate 全部有可重現 PASS 證據。

- [ ] **Step 5: Commit**

```bash
git add tests/manual-e2e.md
git commit -m "test: record macOS reinstall parity and live smoke gate"
```

## Self-Review Checklist

- [ ] 規格覆蓋：interpreter resolver、fresh/repeat/upgrade/parity/Codex absent/registration failure/runtime sentinel、session discovery negative diagnostics、RPC negative diagnostics、GUID/finally/KeepArtifacts、`.gitattributes`、Windows+macOS Py3.11/3.13 CI、manual E2E/docs、macOS reinstall/parity/live smoke 均有對應任務。
- [ ] 佔位掃描：全文不得出現 `TBD`、`TODO`、`implement later`、`fill in details` 或未定義的「適當處理」描述；每個 code step 都有可直接執行的介面、片段與命令。
- [ ] 型別一致性：Task 1 的 `resolve_interpreter`/`Resolve-PythonInterpreter` 被 Task 2 的 manifest normalization/registration 共用；Task 3 的 `safe_diagnostic` 被 Task 4 的 RPC error formatter 以相同 redaction/max-body 語意使用；Task 5 的 `artifactRoot`/`artifactsRetained`/`cleanupError` 與測試輸出欄位一致。
- [ ] 行尾與範圍：本計畫只描述指定檔案的未來變更；建立計畫時不修改 production/test，也不納入既有 EOL-only 工作樹差異。

Execution Route: Subagent-Driven
