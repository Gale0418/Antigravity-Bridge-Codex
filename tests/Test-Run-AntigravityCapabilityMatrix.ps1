$ErrorActionPreference = 'Stop'

$json = & "$PSScriptRoot\..\scripts\Run-AntigravityCapabilityMatrix.ps1" -WorkspacePath 'D:\MyGame' -DryRun
$plan = $json | ConvertFrom-Json

if ($plan.workspacePath -ne 'D:\MyGame') {
    throw "Unexpected workspace path: $($plan.workspacePath)"
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
