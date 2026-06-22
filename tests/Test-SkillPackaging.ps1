$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$pluginManifestPath = Join-Path $repoRoot '.codex-plugin\plugin.json'

if (-not (Test-Path -LiteralPath $pluginManifestPath)) {
    throw "Missing plugin manifest: $pluginManifestPath"
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

Write-Host 'PASS: plugin packaging metadata looks correct'