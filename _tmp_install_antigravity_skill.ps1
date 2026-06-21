$ErrorActionPreference = 'Stop'
$skillRoot = 'C:\Users\USER\.codex\skills\antigravity-gemini-bridge'

if (-not (Test-Path $skillRoot)) {
    New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
}

$sourceRoot = $PSScriptRoot

$items = @(
    "SKILL.md",
    "agents",
    "assets",
    "references",
    "scripts"
)

Write-Host "Installing antigravity-gemini-bridge from $sourceRoot to $skillRoot"
foreach ($item in $items) {
    $srcPath = "$sourceRoot\$item"
    $dstPath = "$skillRoot\$item"
    if (Test-Path $srcPath) {
        if (Test-Path $dstPath) {
            Remove-Item -LiteralPath $dstPath -Recurse -Force
        }
        Copy-Item -LiteralPath $srcPath -Destination $dstPath -Recurse -Force
    }
}
Write-Host "Install completed."