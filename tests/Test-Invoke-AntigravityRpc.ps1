$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\..\scripts\Invoke-AntigravityRpc.ps1"

$trajectoryUri = Get-AntigravityServiceUri -HttpPort 50609 -Method 'GetCascadeTrajectory'
if ($trajectoryUri -ne 'http://127.0.0.1:50609/exa.language_server_pb.LanguageServerService/GetCascadeTrajectory') {
    throw "Unexpected trajectory uri: $trajectoryUri"
}

$tempPath = [System.IO.Path]::GetFullPath($env:TEMP)
$workspaceUri = ConvertTo-AntigravityFileUri -Path $tempPath
$expectedUri = [System.Uri]::new($tempPath).AbsoluteUri
if ($workspaceUri -ne $expectedUri) {
    throw "Unexpected workspace uri: $workspaceUri expected: $expectedUri"
}

$encodedUri = ConvertTo-AntigravityFileUri -Path 'D:\My Game\測試#1.txt'
if ($encodedUri -notmatch '%20' -or $encodedUri -notmatch '%23') {
    throw "Expected encoded file uri, got '$encodedUri'"
}

function Get-AntigravityTrajectory {
    param(
        [string]$CascadeId,
        [int]$Verbosity = 2,
        [psobject]$Session
    )

    return [pscustomobject]@{ steps = @() }
}

try {
    Wait-AntigravityTrajectoryMatch -CascadeId 'timeout-case' -Pattern 'READY' -TimeoutSeconds 0 -PollIntervalSeconds 0 -Session ([pscustomobject]@{}) | Out-Null
    throw 'Expected timeout exception from Wait-AntigravityTrajectoryMatch'
} catch {
    if ($_.Exception.Message -notmatch 'Timed out waiting for pattern') {
        throw "Unexpected timeout error: $($_.Exception.Message)"
    }
}

try {
    $timeoutResult = Wait-AntigravityTrajectoryOutcome -CascadeId 'timeout-case' -Pattern 'READY' -TimeoutSeconds 0 -PollIntervalSeconds 0 -Session ([pscustomobject]@{})
    if (-not $timeoutResult.TimedOut) {
        throw 'Expected timeout outcome to mark TimedOut = true'
    }
    if ($timeoutResult.Matched) {
        throw 'Expected timeout outcome to leave Matched = false'
    }
} catch {
    throw "Unexpected timeout outcome error: $($_.Exception.Message)"
}

Write-Host 'PASS: rpc helper values look correct'
