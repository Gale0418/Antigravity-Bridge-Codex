$ErrorActionPreference = 'Stop'

$env:ANTIGRAVITY_MODEL = 'test-model'
$workspace = Join-Path $env:TEMP 'antigravity matrix dryrun'
New-Item -ItemType Directory -Force -Path $workspace | Out-Null
$resolvedWorkspace = (Resolve-Path -LiteralPath $workspace).Path
$json = & "$PSScriptRoot\..\scripts\Run-AntigravityCapabilityMatrix.ps1" -WorkspacePath $workspace -DryRun
$plan = $json | ConvertFrom-Json

if ($plan.workspacePath -ne $resolvedWorkspace) {
    throw "Unexpected workspace path: $($plan.workspacePath)"
}

$scriptText = Get-Content "$PSScriptRoot\..\scripts\Run-AntigravityCapabilityMatrix.ps1" -Raw
if ($scriptText -match 'MODEL_PLACEHOLDER_M36') {
    throw 'Capability matrix should not use a placeholder default model'
}
if ($scriptText -match 'd:\\MyGame\|file:///d:/MyGame') {
    throw 'Capability matrix still hardcodes D:\MyGame in workspace-awareness checks'
}
if ($scriptText -match '今天 2026-06-21') {
    throw 'Capability matrix still uses conflicting 今天 wording in the fixed-date web probe'
}

$requiredIds = @(
    'roundtrip-response',
    'workspace-awareness',
    'read-existing-file',
    'write-new-file',
    'modify-existing-file',
    'multi-turn-memory',
    'web-access-probe',
    'missing-model-negative-check'
)

foreach ($id in $requiredIds) {
    if ($plan.testIds -notcontains $id) {
        throw "Missing planned test id: $id"
    }
}

Write-Host 'PASS: capability matrix dry-run looks correct'
