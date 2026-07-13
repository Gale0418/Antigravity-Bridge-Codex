$ErrorActionPreference = 'Stop'

$bridgeScriptText = Get-Content (Join-Path $PSScriptRoot '..\scripts\Invoke-AntigravityBridge.ps1') -Raw
if ($bridgeScriptText -notmatch '\[switch\]\$AllowTimeout') {
    throw 'Invoke-AntigravityBridge.ps1 should expose -AllowTimeout for timeout inspection mode'
}
if ($bridgeScriptText -notmatch 'Action ''\$Action'' timed out waiting for pattern') {
    throw 'Invoke-AntigravityBridge.ps1 should throw a timeout error before returning success-shaped JSON'
}
if ($bridgeScriptText -notmatch 'Re-run with -AllowTimeout to inspect partial output\.') {
    throw 'Invoke-AntigravityBridge.ps1 should explain how to opt into timeout inspection mode'
}
if ($bridgeScriptText -match '\[string\]\$WaitPattern\s*=\s*''\(\?s\)\.\+''') {
    throw 'Bridge start/send must not use a broad default wait pattern'
}
if ($bridgeScriptText -notmatch 'New-AntigravityCompletionMarker') {
    throw 'Bridge should generate a unique completion marker when no pattern is supplied'
}
if ($bridgeScriptText -notmatch 'Wait-AntigravityTrajectoryMatchResult') {
    throw 'Bridge should consume the explicit trajectory match result helper'
}
if ($bridgeScriptText -notmatch 'TimeoutSeconds 30') {
    throw 'Bridge smoke action should use a fixed 30-second wait'
}
if ($bridgeScriptText -notmatch 'Action ''\$Action'' failed in cascade') {
    throw 'Bridge should not turn trajectory failures into successful output'
}

function Assert-ThrowsLike {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedText,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    try {
        & $ScriptBlock
        throw "Expected an error for ${Label}, but the command succeeded."
    } catch {
        if ($_.Exception.Message -notmatch [Regex]::Escape($ExpectedText)) {
            throw "Unexpected error for ${Label}: $($_.Exception.Message)"
        }
    }
}

Assert-ThrowsLike -Label 'start validation' -ExpectedText 'requires -OpeningPrompt' -ScriptBlock {
    & "$PSScriptRoot\..\scripts\Invoke-AntigravityBridge.ps1" -Action start
}

Assert-ThrowsLike -Label 'send validation' -ExpectedText 'requires -CascadeId' -ScriptBlock {
    & "$PSScriptRoot\..\scripts\Invoke-AntigravityBridge.ps1" -Action send
}

Assert-ThrowsLike -Label 'trajectory validation' -ExpectedText 'requires -CascadeId' -ScriptBlock {
    & "$PSScriptRoot\..\scripts\Invoke-AntigravityBridge.ps1" -Action trajectory
}

$env:ANTIGRAVITY_MODEL = 'test-model'
$json = & "$PSScriptRoot\..\scripts\Invoke-AntigravityBridge.ps1" -Action matrix -DryRun
$plan = $json | ConvertFrom-Json

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

Write-Host 'PASS: bridge cli validation and dry-run look correct'
