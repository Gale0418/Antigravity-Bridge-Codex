$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$skillText = Get-Content (Join-Path $repoRoot 'SKILL.md') -Raw

if ($skillText -notmatch 'Platform Scope') {
    throw 'SKILL.md should document the current platform scope explicitly'
}
if ($skillText -notmatch 'local loopback Antigravity bridge') {
    throw 'SKILL.md should document the local loopback trust model'
}
if ($skillText -notmatch 'permission prompt') {
    throw 'SKILL.md should tell agents to check Antigravity UI permission prompts on timeout'
}

if (-not (Test-Path (Join-Path $repoRoot '.github\workflows\pester.yml'))) {
    throw 'Missing GitHub Actions workflow for bridge regression tests'
}

Write-Host 'PASS: repository contract docs and CI files look correct'
