$ErrorActionPreference = 'Stop'

$env:ANTIGRAVITY_MODEL = 'test-model'
$systemTemp = [System.IO.Path]::GetTempPath()
$workspace = Join-Path $systemTemp 'antigravity matrix dryrun'
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

$actualIds = @($plan.testIds)
if ($actualIds.Count -ne 8) {
    throw "Expected exactly 8 planned test IDs, got $($actualIds.Count)"
}
if ((@($actualIds | Sort-Object -Unique)).Count -ne $actualIds.Count) {
    throw 'Planned test IDs must be unique'
}
if ((Compare-Object -ReferenceObject ($requiredIds | Sort-Object) -DifferenceObject ($actualIds | Sort-Object))) {
    throw 'Planned test IDs do not exactly match the required capability matrix'
}
Write-Host 'PASS: capability matrix dry-run looks correct'
