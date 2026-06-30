$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\..\scripts\Invoke-AntigravityRpc.ps1"

$rpcScriptText = Get-Content (Join-Path $PSScriptRoot '..\scripts\Invoke-AntigravityRpc.ps1') -Raw
if ($rpcScriptText -notmatch 'elseif \(\$resolved -match ''\^/''\)') {
    throw 'ConvertTo-AntigravityFileUri should include a POSIX absolute-path branch'
}
if ($rpcScriptText -notmatch 'UNC paths are currently not supported') {
    throw 'ConvertTo-AntigravityFileUri should reject UNC paths explicitly'
}
if ($rpcScriptText -notmatch 'Find-AntigravityRecentModel') {
    throw 'Invoke-AntigravityRpc should include recent local model discovery'
}
if ($rpcScriptText -notmatch 'planModel') {
    throw 'Invoke-AntigravityRpc should set plannerConfig.planModel when an internal model enum is available'
}

$trajectoryUri = Get-AntigravityServiceUri -HttpPort 50609 -Method 'GetCascadeTrajectory'
if ($trajectoryUri -ne 'http://127.0.0.1:50609/exa.language_server_pb.LanguageServerService/GetCascadeTrajectory') {
    throw "Unexpected trajectory uri: $trajectoryUri"
}

$systemTemp = [System.IO.Path]::GetTempPath()
$tempPath = [System.IO.Path]::GetFullPath($systemTemp)
$workspaceUri = ConvertTo-AntigravityFileUri -Path $tempPath
$expectedUri = [System.Uri]::new($tempPath).AbsoluteUri
if ($workspaceUri -ne $expectedUri) {
    throw "Unexpected workspace uri: $workspaceUri expected: $expectedUri"
}

$encodedUri = ConvertTo-AntigravityFileUri -Path 'D:\My Game\測試#1.txt'
if ($encodedUri -notmatch '%20' -or $encodedUri -notmatch '%23') {
    throw "Expected encoded file uri, got '$encodedUri'"
}

try {
    ConvertTo-AntigravityFileUri -Path '\\server\share\not-supported.txt' | Out-Null
    throw 'Expected non-Windows paths to fail explicitly'
} catch {
    if ($_.Exception.Message -notmatch 'UNC paths are currently not supported') {
        throw "Unexpected invalid path error: $($_.Exception.Message)"
    }
}

if ($IsMacOS -or $IsLinux) {
    $posixUri = ConvertTo-AntigravityFileUri -Path '/tmp/My Game/測試#1.txt'
    if ($posixUri -notmatch '^file:///tmp/' -or $posixUri -notmatch '%20' -or $posixUri -notmatch '%23') {
        throw "Expected encoded POSIX file uri, got '$posixUri'"
    }
}

Remove-Item Env:ANTIGRAVITY_MODEL -ErrorAction SilentlyContinue
$originalFind = ${function:Find-AntigravityRecentModelSelection}
try {
    ${function:Find-AntigravityRecentModelSelection} = { return (New-AntigravityModelSelection) }
    New-AntigravityCascade -WorkspacePaths @($tempPath) -Session ([pscustomobject]@{}) | Out-Null
    throw 'Expected missing model configuration to fail explicitly'
} catch {
    if ($_.Exception.Message -notmatch 'ANTIGRAVITY_MODEL' -and $_.Exception.Message -notmatch 'recent successful local conversation') {
        throw "Unexpected missing model error: $($_.Exception.Message)"
    }
} finally {
    ${function:Find-AntigravityRecentModelSelection} = $originalFind
}

$conversationDir = Join-Path $systemTemp "antigravity-conversations-$([guid]::NewGuid().Guid)"
New-Item -ItemType Directory -Path $conversationDir | Out-Null
[System.IO.File]::WriteAllBytes(
    (Join-Path $conversationDir 'recent.db'),
    [System.Text.Encoding]::ASCII.GetBytes("trajectory_id`0abc`0gemini-3.1-pro-low`0model_enum`0MODEL_PLACEHOLDER_M36`0display_name`0Gemini 3.1 Pro (Low)")
)
[System.IO.File]::WriteAllBytes(
    (Join-Path $conversationDir 'older.db'),
    [System.Text.Encoding]::ASCII.GetBytes("trajectory_id`0abc`0gpt-oss-120b-medium`0model_enum`0MODEL_PLACEHOLDER_M12")
)
(Get-Item (Join-Path $conversationDir 'older.db')).LastWriteTimeUtc = (Get-Date).AddMinutes(-5)

$discoveredModel = Find-AntigravityRecentModel -ConversationDirectory $conversationDir
if ($discoveredModel -ne 'gemini-3.1-pro-low') {
    throw "Expected latest local model discovery to return gemini-3.1-pro-low, got '$discoveredModel'"
}

$resolvedSelection = Resolve-AntigravityModelSelection -ConversationDirectory $conversationDir
if ($resolvedSelection.ModelId -ne 'gemini-3.1-pro-low') {
    throw "Expected Resolve-AntigravityModelSelection to reuse recent local model id, got '$($resolvedSelection.ModelId)'"
}
if ($resolvedSelection.ModelEnum -ne 'MODEL_PLACEHOLDER_M36') {
    throw "Expected Resolve-AntigravityModelSelection to reuse recent local model enum, got '$($resolvedSelection.ModelEnum)'"
}

$resolvedFallbackModel = Resolve-AntigravityModel -ConversationDirectory $conversationDir
if ($resolvedFallbackModel -ne 'gemini-3.1-pro-low') {
    throw "Expected Resolve-AntigravityModel to expose the model id, got '$resolvedFallbackModel'"
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
