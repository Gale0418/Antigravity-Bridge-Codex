$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$pluginManifestPath = Join-Path $repoRoot '.codex-plugin\plugin.json'
$pythonInstallerPath = Join-Path $repoRoot '_tmp_install_antigravity_skill.py'
$powershellInstallerPath = Join-Path $repoRoot '_tmp_install_antigravity_skill.ps1'
$packagingDocPath = Join-Path $repoRoot 'references\skill-packaging.md'

if (-not (Test-Path -LiteralPath $pluginManifestPath)) {
    throw "Missing plugin manifest: $pluginManifestPath"
}
if (-not (Test-Path -LiteralPath $pythonInstallerPath)) {
    throw "Missing Python installer helper: $pythonInstallerPath"
}
if (-not (Test-Path -LiteralPath $powershellInstallerPath)) {
    throw "Missing PowerShell installer helper: $powershellInstallerPath"
}

$manifest = Get-Content -LiteralPath $pluginManifestPath -Raw | ConvertFrom-Json

if ($manifest.name -ne 'antigravity-gemini-bridge') {
    throw "Unexpected plugin name: $($manifest.name)"
}

if ($manifest.skills -ne './skills/') {
    throw "Unexpected skills path: $($manifest.skills)"
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

Write-Host 'PASS: plugin packaging metadata looks correct'
