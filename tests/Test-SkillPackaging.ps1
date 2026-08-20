$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$pluginManifestPath = Join-Path $repoRoot '.codex-plugin/plugin.json'
$pythonInstallerPath = Join-Path $repoRoot 'scripts/install.py'
$powershellInstallerPath = Join-Path $repoRoot 'scripts/install.ps1'
$packagingDocPath = Join-Path $repoRoot 'references/skill-packaging.md'
$mcpManifestPath = Join-Path $repoRoot '.mcp.json'
$mcpServerPath = Join-Path $repoRoot 'mcp/antigravity_bridge_server.py'
$pythonBridgePath = Join-Path $repoRoot 'scripts/antigravity_bridge.py'
$legacyName = ('antigravity-', 'gemini', '-bridge') -join ''

if (-not (Test-Path -LiteralPath $pluginManifestPath)) {
    throw "Missing plugin manifest: $pluginManifestPath"
}
if (-not (Test-Path -LiteralPath $pythonInstallerPath)) {
    throw "Missing Python installer helper: $pythonInstallerPath"
}
if (-not (Test-Path -LiteralPath $powershellInstallerPath)) {
    throw "Missing PowerShell installer helper: $powershellInstallerPath"
}
if (-not (Test-Path -LiteralPath $mcpManifestPath)) {
    throw "Missing MCP manifest: $mcpManifestPath"
}
if (-not (Test-Path -LiteralPath $mcpServerPath)) {
    throw "Missing MCP server: $mcpServerPath"
}
if (-not (Test-Path -LiteralPath $pythonBridgePath)) {
    throw "Missing Python bridge fallback: $pythonBridgePath"
}

$manifest = Get-Content -LiteralPath $pluginManifestPath -Raw | ConvertFrom-Json

if ($manifest.name -ne 'antigravity-bridge-codex') {
    throw "Unexpected plugin name: $($manifest.name)"
}
if ((Get-Content -LiteralPath $pluginManifestPath -Raw) -match $legacyName) {
    throw "Plugin manifest should not use the legacy $legacyName name"
}

if ($manifest.skills -ne './skills/') {
    throw "Unexpected skills path: $($manifest.skills)"
}
if ($manifest.mcpServers -ne './.mcp.json') {
    throw "Unexpected MCP servers path: $($manifest.mcpServers)"
}
if ($manifest.bundledContentVariant -ne 'legacy-mcp') {
    throw "Unexpected bundled content variant: $($manifest.bundledContentVariant)"
}

$pluginSkillsRoot = Join-Path $repoRoot ($manifest.skills -replace '^\./', '')
$pluginSkillManifestPath = Join-Path $pluginSkillsRoot 'antigravity-bridge-codex/SKILL.md'
if (-not (Test-Path -LiteralPath $pluginSkillManifestPath)) {
    throw "Plugin skills path must contain antigravity-bridge-codex/SKILL.md: $pluginSkillManifestPath"
}
$pluginSkillText = Get-Content -LiteralPath $pluginSkillManifestPath -Raw
if ($pluginSkillText -notmatch '\.\./\.\./SKILL\.md') {
    throw 'Plugin skill wrapper should delegate to the canonical root SKILL.md'
}

$mcpManifest = Get-Content -LiteralPath $mcpManifestPath -Raw | ConvertFrom-Json
$bridgeServer = $mcpManifest.mcpServers.'antigravity-bridge-codex'
if ($bridgeServer.type -ne 'stdio') {
    throw "Expected MCP server type 'stdio' but got '$($bridgeServer.type)'"
}
if ([string]::IsNullOrWhiteSpace($bridgeServer.command)) {
    throw 'Expected MCP server command to be set'
}
if ($IsWindows -or $PSVersionTable.PSEdition -eq 'Desktop') {
    $mcpCommand = Get-Command $bridgeServer.command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($mcpCommand -and $mcpCommand.Source -like '*\WindowsApps\python3.exe') {
        throw 'MCP manifest should not resolve to the Windows Store python3 alias on Windows; prefer python or installer-normalized absolute interpreter paths.'
    }
}

$composerIconPath = Join-Path $repoRoot ($manifest.interface.composerIcon -replace '^\./', '')
if (-not (Test-Path -LiteralPath $composerIconPath)) {
    throw "Missing composer icon asset: $composerIconPath"
}

$logoPath = Join-Path $repoRoot ($manifest.interface.logo -replace '^\./', '')
if (-not (Test-Path -LiteralPath $logoPath)) {
    throw "Missing logo asset: $logoPath"
}

$packagingText = Get-Content -LiteralPath $packagingDocPath -Raw
if ($packagingText -notmatch 'install\.py') {
    throw 'Packaging docs should mention the Python installer for macOS/local non-PowerShell setups'
}
if ($packagingText -notmatch 'macOS') {
    throw 'Packaging docs should document macOS installation explicitly'
}
if ($packagingText -notmatch '\.mcp\.json') {
    throw 'Packaging docs should mention MCP manifest packaging'
}
if ($packagingText -notmatch 'legacy-mcp') {
    throw 'Packaging docs should document the legacy-mcp plugin variant'
}
if ($packagingText -notmatch 'absolute Python') {
    throw 'Packaging docs should document absolute Python command normalization'
}

$pythonInstallerText = Get-Content -LiteralPath $pythonInstallerPath -Raw
if ($pythonInstallerText -notmatch '"mcp"') {
    throw 'Python installer should copy the mcp directory'
}
if ($pythonInstallerText -notmatch '"\.mcp\.json"') {
    throw 'Python installer should copy .mcp.json'
}
if ($pythonInstallerText -match $legacyName) {
    throw "Python installer should not use the legacy $legacyName name"
}
if ($pythonInstallerText -notmatch 'normalize_mcp_manifest') {
    throw 'Python installer should normalize the installed MCP manifest'
}
if ($pythonInstallerText -notmatch 'resolve_mcp_python_command') {
    throw 'Python installer should resolve a stable MCP Python command'
}
if ($pythonInstallerText -notmatch 'is_windows_store_python_alias') {
    throw 'Python installer should skip Windows Store Python aliases'
}
if ($pythonInstallerText -notmatch 'STABLE_MCP_SERVER_NAME = "antigravity_bridge_codex"') {
    throw 'Python installer should register the stable user MCP server name'
}
if ($pythonInstallerText -notmatch '"mcp",\s*"add"') {
    throw 'Python installer should add a stable user MCP server'
}
if ($pythonInstallerText -notmatch 'args.*resolve') {
    throw 'Python installer should normalize MCP args[0] to absolute path'
}
if ($pythonInstallerText -notmatch 'cwd.*resolve') {
    throw 'Python installer should normalize MCP cwd to absolute path'
}

$powershellInstallerText = Get-Content -LiteralPath $powershellInstallerPath -Raw
if ($powershellInstallerText -notmatch "'mcp'") {
    throw 'PowerShell installer should copy the mcp directory'
}
if ($powershellInstallerText -notmatch "'\.mcp\.json'") {
    throw 'PowerShell installer should copy .mcp.json'
}
if ($powershellInstallerText -match $legacyName) {
    throw "PowerShell installer should not use the legacy $legacyName name"
}
if ($powershellInstallerText -notmatch 'Set-InstalledMcpInterpreter') {
    throw 'PowerShell installer should normalize the installed MCP manifest'
}
if ($powershellInstallerText -notmatch 'Resolve-McpPythonCommand') {
    throw 'PowerShell installer should resolve a stable MCP Python command'
}
if ($powershellInstallerText -notmatch 'Test-IsWindowsStorePythonAlias') {
    throw 'PowerShell installer should skip Windows Store Python aliases'
}
if ($powershellInstallerText -notmatch "stableMcpServerName = 'antigravity_bridge_codex'") {
    throw 'PowerShell installer should register the stable user MCP server name'
}
if ($powershellInstallerText -notmatch "'mcp', 'add'") {
    throw 'PowerShell installer should add a stable user MCP server'
}
if ($powershellInstallerText -notmatch 'IsPathRooted') {
    throw 'PowerShell installer should check IsPathRooted for MCP server relative paths'
}
if ($powershellInstallerText -notmatch 'GetFullPath') {
    throw 'PowerShell installer should resolve MCP server paths using GetFullPath'
}

Write-Host 'PASS: plugin packaging metadata looks correct'
