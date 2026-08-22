$ErrorActionPreference = 'Stop'
$isWindowsPlatform = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [System.Runtime.InteropServices.OSPlatform]::Windows
)

$bridgeScript = Join-Path $PSScriptRoot '..\scripts\Invoke-AntigravityBridge.ps1'
$bridgeScriptText = Get-Content -LiteralPath $bridgeScript -Raw -Encoding utf8

if ($bridgeScriptText -notmatch "\[ValidateSet\('auto', 'agy', 'rpc'\)\]") { throw 'Bridge should expose auto, agy, and rpc transports' }
if ($bridgeScriptText -notmatch ('\[string\]\' + '$' + "Transport = 'auto'")) { throw 'Bridge should default conversation actions to visible-first auto' }
if ($bridgeScriptText -notmatch "ArgumentList.Add\('--output-format'\)" -or $bridgeScriptText -notmatch "ArgumentList.Add\('json'\)") { throw 'Bridge should request JSON receipts from agy' }
if ($bridgeScriptText -notmatch "ArgumentList.Add\('--conversation'\)") { throw 'Bridge should resume conversations with agy --conversation' }
if ($bridgeScriptText -notmatch "return 'gemini-3.6-flash-high'") { throw 'Bridge should use the required default model' }
if ($bridgeScriptText -notmatch 'process.Kill\(\$true\)') { throw 'Bridge must terminate the agy process tree on timeout' }
if ($bridgeScriptText -notmatch "transport = 'agy'" -or $bridgeScriptText -notmatch 'conversationId' -or $bridgeScriptText -notmatch 'elapsedSeconds') { throw 'Bridge should emit a structured agy receipt' }
if ($bridgeScriptText -notmatch 'Invoke-VisibleRpcPrompt') { throw 'Bridge should include the visible RPC transport' }
if ($bridgeScriptText -notmatch 'ANTIGRAVITY_BRIDGE_MARKER_' -or $bridgeScriptText -notmatch '\[regex\]::Escape\(\$marker\)') { throw 'Visible RPC must wait for a unique completion marker' }

function Assert-ThrowsLike {
    param([scriptblock]$ScriptBlock, [string]$ExpectedText, [string]$Label)
    try { & $ScriptBlock; throw "Expected an error for ${Label}, but the command succeeded." } catch {
        if ($_.Exception.Message -notmatch [Regex]::Escape($ExpectedText)) { throw "Unexpected error for ${Label}: $($_.Exception.Message)" }
    }
}

Assert-ThrowsLike -Label 'start validation' -ExpectedText 'requires -OpeningPrompt' -ScriptBlock { & $bridgeScript -Action start }
Assert-ThrowsLike -Label 'send validation' -ExpectedText 'requires -ConversationId' -ScriptBlock { & $bridgeScript -Action send }
Assert-ThrowsLike -Label 'trajectory validation' -ExpectedText 'requires -CascadeId' -ScriptBlock { & $bridgeScript -Action trajectory }
Assert-ThrowsLike -Label 'rpc validation' -ExpectedText 'requires -OpeningPrompt' -ScriptBlock { & $bridgeScript -Action start -Transport rpc }

# Actual offline mock for the Bridge RPC flow: no language-server process is used.
$visibleRpcMatch = [regex]::Match($bridgeScriptText, '(?s)(function Invoke-VisibleRpcPrompt \{.*?\r?\n\})\r?\nfunction Invoke-LegacyRpcAction')
if (-not $visibleRpcMatch.Success) { throw 'Could not extract Invoke-VisibleRpcPrompt for offline RPC testing.' }
$offlineRpcRoot = Join-Path ([System.IO.Path]::GetTempPath()) "antigravity-bridge-rpc-$([guid]::NewGuid().Guid)"
[System.IO.Directory]::CreateDirectory($offlineRpcRoot) | Out-Null
$offlineRpcMock = [string]::Join("`n", @(
    'function Get-AntigravitySessionInfo { return [pscustomobject]@{ HttpPort = 1; CsrfToken = "offline" } }',
    'function Resolve-AntigravityModelSelection { param([string]$Model) return [pscustomobject]@{ ModelId = $Model; ModelEnum = "" } }',
    'function New-AntigravityCascade { param([string]$Model,[string[]]$WorkspacePaths,[string]$CascadeId,[datetime]$DeadlineUtc,[psobject]$Session) if ($env:ANTIGRAVITY_OFFLINE_SCENARIO -eq "predispatch") { throw "offline start failure" }; return [pscustomobject]@{ CascadeId = "offline-server-cascade" } }',
    'function Send-AntigravityMessage { param([string]$CascadeId,[string]$Text,[string]$Model,[switch]$OmitRequestedModel,[datetime]$DeadlineUtc,[psobject]$Session) if ([string]::IsNullOrWhiteSpace($CascadeId)) { throw "offline send did not receive a cascade id" }; if ($env:ANTIGRAVITY_OFFLINE_REQUIRE_CONFIG -eq "true" -and $OmitRequestedModel) { throw "high-level sends must include declarative planner config" }; return [pscustomobject]@{ accepted = $true } }',
    'function Wait-AntigravityTrajectoryMatchResult { param([string]$CascadeId,[string]$Pattern,[datetime]$DeadlineUtc,[psobject]$Session) if ($env:ANTIGRAVITY_OFFLINE_SCENARIO -eq "timeout") { return [pscustomobject]@{ matched = $false; timedOut = $true; response = ""; failure = "" } }; return [pscustomobject]@{ matched = $true; timedOut = $false; response = "OFFLINE_OK"; failure = "" } }'
))
$offlineLauncher = $visibleRpcMatch.Groups[1].Value + "`n`$result = Invoke-VisibleRpcPrompt -Prompt 'offline prompt' -ActionName `$env:ANTIGRAVITY_OFFLINE_ACTION -CascadeId `$env:ANTIGRAVITY_OFFLINE_CASCADE -Model 'offline-model' -WorkspacePath `$env:ANTIGRAVITY_OFFLINE_WORKSPACE -DeadlineUtc ([datetime]::UtcNow.AddSeconds(5)) -RequestId 'request-1' -MissionId 'mission-1' -LaneId 'lane-1'`n`$result | ConvertTo-Json -Depth 8"
[System.IO.File]::WriteAllText((Join-Path $offlineRpcRoot 'Invoke-AntigravityRpc.ps1'), $offlineRpcMock, [System.Text.UTF8Encoding]::new($false))
$offlineLauncherPath = Join-Path $offlineRpcRoot 'Run-OfflineBridgeRpc.ps1'
[System.IO.File]::WriteAllText($offlineLauncherPath, $offlineLauncher, [System.Text.UTF8Encoding]::new($false))
$previousOfflineScenario = $env:ANTIGRAVITY_OFFLINE_SCENARIO; $previousOfflineAction = $env:ANTIGRAVITY_OFFLINE_ACTION; $previousOfflineCascade = $env:ANTIGRAVITY_OFFLINE_CASCADE; $previousOfflineWorkspace = $env:ANTIGRAVITY_OFFLINE_WORKSPACE; $previousOfflineRequireConfig = $env:ANTIGRAVITY_OFFLINE_REQUIRE_CONFIG
try {
    $env:ANTIGRAVITY_OFFLINE_SCENARIO = 'success'; $env:ANTIGRAVITY_OFFLINE_ACTION = 'start'; $env:ANTIGRAVITY_OFFLINE_CASCADE = ''; $env:ANTIGRAVITY_OFFLINE_WORKSPACE = (Resolve-Path .).Path; $env:ANTIGRAVITY_OFFLINE_REQUIRE_CONFIG = 'true'
    $offlineStart = (& $offlineLauncherPath) | ConvertFrom-Json
    if ($offlineStart.cascadeId -ne 'offline-server-cascade' -or $offlineStart.conversationId -ne 'offline-server-cascade' -or $offlineStart.requestId -ne 'request-1' -or $offlineStart.missionId -ne 'mission-1' -or $offlineStart.laneId -ne 'lane-1') { throw 'Offline RPC start should round-trip the server cascade id and correlation ids.' }
    $env:ANTIGRAVITY_OFFLINE_SCENARIO = 'timeout'; $env:ANTIGRAVITY_OFFLINE_ACTION = 'send'; $env:ANTIGRAVITY_OFFLINE_CASCADE = 'existing-offline-cascade'
    $offlineSendTimeout = (& $offlineLauncherPath) | ConvertFrom-Json
    if ($offlineSendTimeout.status -ne 'timeout' -or $offlineSendTimeout.safe_to_fallback -or $offlineSendTimeout.fallbackUsed -or $offlineSendTimeout.delivery_state -ne 'DELIVERY_UNKNOWN') { throw 'A send timeout after dispatch must not fall back to a second transport.' }
    $env:ANTIGRAVITY_OFFLINE_SCENARIO = 'predispatch'; $env:ANTIGRAVITY_OFFLINE_ACTION = 'start'; $env:ANTIGRAVITY_OFFLINE_CASCADE = ''
    $offlinePreDispatch = (& $offlineLauncherPath) | ConvertFrom-Json
    if (-not $offlinePreDispatch.safe_to_fallback -or $offlinePreDispatch.delivery_state -ne 'PRE_DISPATCH_FAILED') { throw 'A pre-dispatch RPC failure should remain eligible for auto fallback.' }
} finally {
    Remove-Item -LiteralPath $offlineRpcRoot -Recurse -Force -ErrorAction SilentlyContinue
    $env:ANTIGRAVITY_OFFLINE_SCENARIO = $previousOfflineScenario; $env:ANTIGRAVITY_OFFLINE_ACTION = $previousOfflineAction; $env:ANTIGRAVITY_OFFLINE_CASCADE = $previousOfflineCascade; $env:ANTIGRAVITY_OFFLINE_WORKSPACE = $previousOfflineWorkspace; $env:ANTIGRAVITY_OFFLINE_REQUIRE_CONFIG = $previousOfflineRequireConfig
}

$previousAntigravityModel = $env:ANTIGRAVITY_MODEL
try {
$env:ANTIGRAVITY_MODEL = ''

$previousLocalAppData = $env:LOCALAPPDATA
$previousUserProfile = $env:USERPROFILE
$previousFakeArgsFile = $env:AGY_FAKE_ARGS_FILE
$previousTranscriptDirectory = $env:ANTIGRAVITY_BRIDGE_TRANSCRIPT_DIR
$env:ANTIGRAVITY_BRIDGE_TRANSCRIPT_DIR = ''
$testLocalAppData = Join-Path ([System.IO.Path]::GetTempPath()) "agy-transcript-$([guid]::NewGuid().Guid)"
[System.IO.Directory]::CreateDirectory($testLocalAppData) | Out-Null
$testUserProfile = Join-Path ([System.IO.Path]::GetTempPath()) "agy-profile-$([guid]::NewGuid().Guid)"
$projectConfigRoot = Join-Path (Join-Path (Join-Path $testUserProfile '.gemini') 'config') 'projects'
[System.IO.Directory]::CreateDirectory($projectConfigRoot) | Out-Null
$resolvedWorkspacePath = (Resolve-Path .).Path
$workspaceUri = [System.Uri]::new($resolvedWorkspacePath).AbsoluteUri
$projectFixture = [pscustomobject]@{ id = 'fixture-project'; projectResources = [pscustomobject]@{ resources = @([pscustomobject]@{ gitFolder = [pscustomobject]@{ folderUri = $workspaceUri; defaultBranch = 'main' } }) } }
[System.IO.File]::WriteAllText((Join-Path $projectConfigRoot 'fixture-project.json'), ($projectFixture | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
$env:LOCALAPPDATA = $testLocalAppData
$env:USERPROFILE = $testUserProfile
$fakeArgsFile = Join-Path $testLocalAppData 'agy-args.txt'
$env:AGY_FAKE_ARGS_FILE = $fakeArgsFile
$fakeAgyExtension = if ($isWindowsPlatform) { '.cmd' } else { '.sh' }
$fakeAgy = Join-Path ([System.IO.Path]::GetTempPath()) "agy-fake-$([guid]::NewGuid().Guid)$fakeAgyExtension"
$fakeAgyContent = if ($isWindowsPlatform) {
    [string]::Join([Environment]::NewLine, @('@echo off', 'if not "%AGY_FAKE_ARGS_FILE%"=="" echo %*>"%AGY_FAKE_ARGS_FILE%"', 'echo {"conversation_id":"test-conversation","status":"SUCCESS","response":"AGY_OK","error":null}', ''))
} else {
    [string]::Join("`n", @('#!/bin/sh', 'if [ -n "$AGY_FAKE_ARGS_FILE" ]; then printf ''%s\n'' "$*" > "$AGY_FAKE_ARGS_FILE"; fi', 'printf ''%s\n'' ''{"conversation_id":"test-conversation","status":"SUCCESS","response":"AGY_OK","error":null}''', ''))
}
[System.IO.File]::WriteAllText($fakeAgy, $fakeAgyContent, [System.Text.ASCIIEncoding]::new())
if (-not $isWindowsPlatform) { & chmod u+x $fakeAgy }
try {
    $receipt = (& $bridgeScript -Action start -OpeningPrompt 'hello' -NoIntro -Transport agy -AgyPath $fakeAgy -TimeoutSeconds 5) | ConvertFrom-Json
    $fakeArgs = Get-Content -LiteralPath $fakeArgsFile -Raw -Encoding utf8
    if ($receipt.projectId -ne 'fixture-project' -or $receipt.projectSource -ne 'workspace_match' -or $fakeArgs -notmatch '--project fixture-project') {
        throw 'New agy conversations should bind to the longest matching Antigravity project.'
    }
    if ([string]::IsNullOrWhiteSpace([string]$receipt.transcriptPath) -or -not (Test-Path -LiteralPath $receipt.transcriptPath)) {
        throw 'Successful agy calls should create a local transcript and return transcriptPath.'
    }
    $transcript = Get-Content -LiteralPath $receipt.transcriptPath -Raw -Encoding utf8
    if ($transcript -notmatch '### Prompt' -or $transcript -notmatch 'AGY_OK') {
        throw 'Transcript should record the prompt and response.'
    }
    $noTranscriptReceipt = (& $bridgeScript -Action start -OpeningPrompt 'hello' -NoIntro -Transport agy -AgyPath $fakeAgy -TimeoutSeconds 5 -NoTranscript) | ConvertFrom-Json
    if ($noTranscriptReceipt.transcriptPath -or $noTranscriptReceipt.transcriptError) {
        throw 'NoTranscript should suppress transcript output without failing the agy receipt.'
    }
    if ($receipt.transport -ne 'agy' -or $receipt.legacy -or -not $receipt.usable -or $receipt.conversationId -ne 'test-conversation' -or $receipt.response -ne 'AGY_OK' -or $receipt.model -ne 'gemini-3.6-flash-high' -or $receipt.workspacePath -ne (Resolve-Path .).Path -or $receipt.resumeCommand -notmatch 'test-conversation') {
        throw 'Expected the official agy receipt to preserve transport, conversation, response, and default model.'
    }
} finally {
    Remove-Item -LiteralPath $fakeAgy -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $testLocalAppData -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $testUserProfile -Recurse -Force -ErrorAction SilentlyContinue
    $env:LOCALAPPDATA = $previousLocalAppData
    $env:USERPROFILE = $previousUserProfile
    $env:AGY_FAKE_ARGS_FILE = $previousFakeArgsFile
    $env:ANTIGRAVITY_BRIDGE_TRANSCRIPT_DIR = $previousTranscriptDirectory
}

$slowAgyExtension = if ($isWindowsPlatform) { '.cmd' } else { '.sh' }
$slowAgy = Join-Path ([System.IO.Path]::GetTempPath()) "agy-slow-$([guid]::NewGuid().Guid)$slowAgyExtension"
$slowAgyContent = if ($isWindowsPlatform) { "@echo off`r`nping 127.0.0.1 -n 20 >nul`r`n" } else { "#!/bin/sh`nsleep 20`n" }
[System.IO.File]::WriteAllText($slowAgy, $slowAgyContent, [System.Text.ASCIIEncoding]::new())
if (-not $isWindowsPlatform) { & chmod u+x $slowAgy }
$pwsh = (Get-Command pwsh -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
try {
    $timeoutJson = & $pwsh -NoLogo -NoProfile -File $bridgeScript -Action smoke -Transport agy -AgyPath $slowAgy -TimeoutSeconds 1
    if ($LASTEXITCODE -eq 0) { throw 'A non-allowed agy timeout must produce a non-zero exit code.' }
    $timeoutReceipt = $timeoutJson | ConvertFrom-Json
    if ($timeoutReceipt.status -ne 'timeout' -or -not $timeoutReceipt.timedOut -or -not $timeoutReceipt.failure) {
        throw 'Timeout receipt must retain status, timedOut, and failure compatibility fields.'
    }

    $allowedTimeoutJson = & $pwsh -NoLogo -NoProfile -File $bridgeScript -Action smoke -Transport agy -AgyPath $slowAgy -TimeoutSeconds 1 -AllowTimeout
    if ($LASTEXITCODE -ne 0) { throw 'AllowTimeout should allow only the timeout receipt to exit successfully.' }
    $allowedTimeoutReceipt = $allowedTimeoutJson | ConvertFrom-Json
    if ($allowedTimeoutReceipt.status -ne 'timeout' -or -not $allowedTimeoutReceipt.timedOut) {
        throw 'AllowTimeout must preserve the timeout receipt.'
    }
} finally {
    Remove-Item -LiteralPath $slowAgy -Force -ErrorAction SilentlyContinue
}
$env:ANTIGRAVITY_MODEL = 'test-model'
$json = & $bridgeScript -Action matrix -Transport rpc -DryRun
$plan = $json | ConvertFrom-Json
$requiredIds = @('roundtrip-response', 'workspace-awareness', 'read-existing-file', 'write-new-file', 'modify-existing-file', 'multi-turn-memory', 'web-access-probe', 'missing-model-negative-check')
foreach ($id in $requiredIds) { if ($plan.testIds -notcontains $id) { throw "Missing planned test id: $id" } }

Write-Host 'PASS: bridge CLI official agy transport and explicit RPC diagnostics look correct'
} finally {
    $env:ANTIGRAVITY_MODEL = $previousAntigravityModel
}
