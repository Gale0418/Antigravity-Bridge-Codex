$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$pluginManifestPath = Join-Path $repoRoot '.codex-plugin\plugin.json'
$pythonInstallerPath = Join-Path $repoRoot '_tmp_install_antigravity_skill.py'
$powershellInstallerPath = Join-Path $repoRoot '_tmp_install_antigravity_skill.ps1'
$packagingDocPath = Join-Path $repoRoot 'references\skill-packaging.md'
$mcpManifestPath = Join-Path $repoRoot '.mcp.json'
$mcpServerPath = Join-Path $repoRoot 'mcp\antigravity_bridge_server.py'
$pythonBridgePath = Join-Path $repoRoot 'scripts\antigravity_bridge.py'

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

if ($manifest.name -ne 'antigravity-gemini-bridge') {
    throw "Unexpected plugin name: $($manifest.name)"
}

if ($manifest.skills -ne './skills/') {
    throw "Unexpected skills path: $($manifest.skills)"
}
if ($manifest.mcpServers -ne './.mcp.json') {
    throw "Unexpected MCP servers path: $($manifest.mcpServers)"
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
if ($packagingText -notmatch '_tmp_install_antigravity_skill.py') {
    throw 'Packaging docs should mention the Python installer for macOS/local non-PowerShell setups'
}
if ($packagingText -notmatch 'macOS') {
    throw 'Packaging docs should document macOS installation explicitly'
}
if ($packagingText -notmatch '\.mcp\.json') {
    throw 'Packaging docs should mention MCP manifest packaging'
}

$pythonInstallerText = Get-Content -LiteralPath $pythonInstallerPath -Raw
if ($pythonInstallerText -notmatch '"mcp"') {
    throw 'Python installer should copy the mcp directory'
}
if ($pythonInstallerText -notmatch '"\.mcp\.json"') {
    throw 'Python installer should copy .mcp.json'
}

$powershellInstallerText = Get-Content -LiteralPath $powershellInstallerPath -Raw
if ($powershellInstallerText -notmatch "'mcp'") {
    throw 'PowerShell installer should copy the mcp directory'
}
if ($powershellInstallerText -notmatch "'\.mcp\.json'") {
    throw 'PowerShell installer should copy .mcp.json'
}

Write-Host 'PASS: plugin packaging metadata looks correct'
