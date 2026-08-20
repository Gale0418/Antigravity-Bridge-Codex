#requires -Version 7.0

param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('discover', 'matrix', 'start', 'send', 'smoke', 'trajectory')]
    [string]$Action,

    [string]$WorkspacePath = (Get-Location).Path,
    [string]$Model = '',
    [ValidateSet('auto', 'agy', 'rpc')]
    [string]$Transport = 'auto',
    [string]$AgyPath = '',
    [ValidateRange(1, 1800)]
    [int]$TimeoutSeconds = 90,

    [switch]$DryRun,
    [string]$OpeningPrompt,
    [ValidateSet('cute', 'professional')]
    [string]$IntroStyle = 'cute',
    [switch]$NoIntro,
    [string]$WaitPattern = '',
    [string]$Text,
    [switch]$AllowTimeout,
    [switch]$OmitRequestedModel,
    [string]$CascadeId,
    [string]$ConversationId,
    [int]$Verbosity = 2,
    [switch]$ShowSecret,
    [switch]$NoTranscript,
    [string]$TranscriptDirectory = '',
    [string]$ProjectId = '',
    [string]$RequestId = '',
    [string]$MissionId = '',
    [string]$LaneId = ''
)

$ErrorActionPreference = 'Stop'
$script:AntigravityUtf8Encoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $script:AntigravityUtf8Encoding
[Console]::InputEncoding = $script:AntigravityUtf8Encoding

function Get-ConversationIntro {
    param([string]$Style)
    if ($Style -eq 'professional') {
        return '我是 Codex，負責規劃、整理和驗收；你負責在 Antigravity 這邊幫忙執行或一起想辦法。接下來請和我協作完成同一個任務，資訊不足就直接提醒我。'
    }
    return '我是 Codex，今天一起來幫主人做事的搭檔。我負責規劃、整理和驗收，你負責在 Antigravity 這邊幫忙執行或一起想辦法；我們像家人聊天一樣合作就好，資訊不夠就直接提醒我。'
}

function Resolve-AgyExecutable {
    param([string]$Path)
    $defaultAgyPath = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'agy\bin\agy.exe' } else { '' }
    $candidates = @($Path, $env:ANTIGRAVITY_AGY_PATH, $defaultAgyPath, 'agy') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    foreach ($candidate in $candidates) {
        if ([System.IO.Path]::IsPathRooted($candidate)) {
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return (Resolve-Path -LiteralPath $candidate).Path }
            continue
        }
        $command = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { return $command.Source }
    }
    throw 'Official agy CLI was not found. Install agy or pass -AgyPath; RPC is available only with explicit -Transport rpc.'
}

function Resolve-AgyModel {
    param([string]$RequestedModel)
    if (-not [string]::IsNullOrWhiteSpace($RequestedModel)) { return $RequestedModel.Trim() }
    if (-not [string]::IsNullOrWhiteSpace($env:ANTIGRAVITY_MODEL)) { return $env:ANTIGRAVITY_MODEL.Trim() }
    return 'gemini-3.6-flash-high'
}

function ConvertFrom-AgyJson {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    try { return $Text | ConvertFrom-Json -ErrorAction Stop } catch { return $null }
}

function Protect-AgyTranscriptText {
    param([string]$Value)
    if ($null -eq $Value) { return '' }
    $safe = $Value
    $safe = [regex]::Replace($safe, '(?im)\b(csrf(?:[_-]?token)?|api[_-]?key|access[_-]?token|authorization)\b\s*[:=]\s*\S+', '$1: <redacted>')
    return [regex]::Replace($safe, '(?i)\bBearer\s+\S+', 'Bearer <redacted>')
}

function Add-AgyTranscript {
    param(
        [Parameter(Mandatory = $true)][psobject]$Receipt,
        [Parameter(Mandatory = $true)][string]$Prompt,
        [string]$WorkspacePath,
        [string]$TranscriptDirectory,
        [switch]$Disabled
    )

    $Receipt | Add-Member -NotePropertyName transcriptPath -NotePropertyValue '' -Force
    $Receipt | Add-Member -NotePropertyName transcriptError -NotePropertyValue '' -Force
    if ($Disabled -or [string]::IsNullOrWhiteSpace([string]$Receipt.conversationId)) { return }
    try {
        $localAppData = if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { [Environment]::GetFolderPath('LocalApplicationData') } else { $env:LOCALAPPDATA }
        $root = if (-not [string]::IsNullOrWhiteSpace($TranscriptDirectory)) { $TranscriptDirectory } elseif (-not [string]::IsNullOrWhiteSpace($env:ANTIGRAVITY_BRIDGE_TRANSCRIPT_DIR)) { $env:ANTIGRAVITY_BRIDGE_TRANSCRIPT_DIR } else { Join-Path $localAppData 'AntigravityBridge\conversations' }
        [System.IO.Directory]::CreateDirectory($root) | Out-Null
        $fileName = [regex]::Replace([string]$Receipt.conversationId, '[' + [regex]::Escape((-join [System.IO.Path]::GetInvalidFileNameChars())) + ']', '_') + '.md'
        $path = Join-Path $root $fileName
        $entry = @(
            "`n## $([DateTime]::UtcNow.ToString('o')) UTC",
            "- action: $($Receipt.action)",
            "- model: $(Protect-AgyTranscriptText ([string]$Receipt.model))",
            "- workspace: $(Protect-AgyTranscriptText $WorkspacePath)",
            "- status: $($Receipt.status)",
            '', '### Prompt', (Protect-AgyTranscriptText $Prompt), '', '### Response', (Protect-AgyTranscriptText ([string]$Receipt.response)), '', '### Error', (Protect-AgyTranscriptText ([string]$Receipt.error)), ''
        ) -join "`n"
        [System.IO.File]::AppendAllText($path, $entry, [System.Text.UTF8Encoding]::new($false))
        $Receipt.transcriptPath = $path
    } catch {
        $Receipt.transcriptError = $_.Exception.Message
    }
}
function Resolve-AgyProject {
    param([string]$WorkspacePath, [string]$ExplicitProjectId)
    if (-not [string]::IsNullOrWhiteSpace($ExplicitProjectId)) {
        return [pscustomobject]@{ Id = $ExplicitProjectId.Trim(); Source = 'explicit' }
    }
    $best = $null
    try {
        $workspace = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $WorkspacePath -ErrorAction Stop).Path).TrimEnd('\', '/')
        $projectsRoot = Join-Path $env:USERPROFILE '.gemini\config\projects'
        foreach ($file in Get-ChildItem -LiteralPath $projectsRoot -Filter '*.json' -File -ErrorAction SilentlyContinue) {
            try { $config = Get-Content -LiteralPath $file.FullName -Raw -Encoding utf8 | ConvertFrom-Json -ErrorAction Stop } catch { continue }
            $id = if (-not [string]::IsNullOrWhiteSpace([string]$config.id)) { [string]$config.id } else { $file.BaseName }
            foreach ($resource in @($config.projectResources.resources)) {
                $uri = if (-not [string]::IsNullOrWhiteSpace([string]$resource.folderUri)) { [string]$resource.folderUri } elseif (-not [string]::IsNullOrWhiteSpace([string]$resource.gitFolder.folderUri)) { [string]$resource.gitFolder.folderUri } else { [string]$resource.localFolder.folderUri }
                if ($uri -notmatch '^file:///') { continue }
                try {
                    $localPath = ([uri]$uri).LocalPath
                    if ($localPath -match '^/[A-Za-z]:/') { $localPath = $localPath.Substring(1) }
                    $candidate = [System.IO.Path]::GetFullPath($localPath).TrimEnd('\', '/')
                } catch { continue }
                $same = $workspace.Equals($candidate, [System.StringComparison]::OrdinalIgnoreCase)
                $under = $workspace.StartsWith($candidate + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
                if (($same -or $under) -and (($null -eq $best) -or $candidate.Length -gt $best.Path.Length)) {
                    $best = [pscustomobject]@{ Id = $id; Path = $candidate }
                }
            }
        }
    } catch { }
    if ($best -and $best.Id) { return [pscustomobject]@{ Id = $best.Id; Source = 'workspace_match' } }
    return [pscustomobject]@{ Id = ''; Source = '' }
}

function Invoke-AgyPrompt {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [string]$ConversationId = '',
        [Parameter(Mandatory = $true)][string]$Model,
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][int]$DeadlineSeconds,
        [string]$WorkspacePath,
        [string]$ActionName,
        [psobject]$Project
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $process = $null
    try {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $Executable
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.CreateNoWindow = $true
        [void]$startInfo.ArgumentList.Add('-p')
        [void]$startInfo.ArgumentList.Add($Prompt)
        [void]$startInfo.ArgumentList.Add('--output-format')
        [void]$startInfo.ArgumentList.Add('json')
        [void]$startInfo.ArgumentList.Add('--model')
        [void]$startInfo.ArgumentList.Add($Model)
        $resolvedWorkspacePath = ''
        if (-not [string]::IsNullOrWhiteSpace($WorkspacePath)) {
            $resolvedWorkspacePath = (Resolve-Path -LiteralPath $WorkspacePath -ErrorAction Stop).Path
            $startInfo.WorkingDirectory = $resolvedWorkspacePath
            [void]$startInfo.ArgumentList.Add('--add-dir')
            [void]$startInfo.ArgumentList.Add($resolvedWorkspacePath)
        }
        [void]$startInfo.ArgumentList.Add('--print-timeout')
        [void]$startInfo.ArgumentList.Add((([Math]::Max(1, $DeadlineSeconds - 5)).ToString()) + 's')
        if ([string]::IsNullOrWhiteSpace($ConversationId) -and $Project -and -not [string]::IsNullOrWhiteSpace([string]$Project.Id)) {
            [void]$startInfo.ArgumentList.Add('--project')
            [void]$startInfo.ArgumentList.Add([string]$Project.Id)
        }
        if (-not [string]::IsNullOrWhiteSpace($ConversationId)) {
            [void]$startInfo.ArgumentList.Add('--conversation')
            [void]$startInfo.ArgumentList.Add($ConversationId)
        }
        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $timedOut = -not $process.WaitForExit($DeadlineSeconds * 1000)
        $killFailed = ''
        $killGraceExpired = $false
        if ($timedOut) {
            try {
                if (-not $process.HasExited) { $process.Kill($true) }
            } catch {
                $killFailed = "Unable to terminate agy process tree: $($_.Exception.Message)"
            }
            if (-not $process.WaitForExit(5000)) {
                $killGraceExpired = $true
                if ([string]::IsNullOrWhiteSpace($killFailed)) {
                    $killFailed = 'agy process did not exit within the 5-second termination grace period.'
                }
            }
        }

        $stdout = ''
        $stderr = ''
        $streamReadError = ''
        try {
            if (-not $stdoutTask.IsCompleted) { [void]$stdoutTask.Wait(1000) }
            if ($stdoutTask.Status -eq [System.Threading.Tasks.TaskStatus]::RanToCompletion) {
                $stdout = $stdoutTask.GetAwaiter().GetResult()
            }
        } catch {
            $streamReadError = "Unable to read agy stdout: $($_.Exception.Message)"
        }
        try {
            if (-not $stderrTask.IsCompleted) { [void]$stderrTask.Wait(1000) }
            if ($stderrTask.Status -eq [System.Threading.Tasks.TaskStatus]::RanToCompletion) {
                $stderr = $stderrTask.GetAwaiter().GetResult()
            }
        } catch {
            if ([string]::IsNullOrWhiteSpace($streamReadError)) {
                $streamReadError = "Unable to read agy stderr: $($_.Exception.Message)"
            }
        }
        $parsed = ConvertFrom-AgyJson -Text $stdout
        $cliError = if ($parsed -and $null -ne $parsed.error) { [string]$parsed.error } elseif ($stderr) { $stderr.Trim() } elseif ($streamReadError) { $streamReadError } elseif (-not $parsed -and -not $killGraceExpired) { 'agy did not return a JSON receipt.' } else { '' }
        $status = if ($killGraceExpired) { 'kill_failed' } elseif ($timedOut) { 'timeout' } elseif ($parsed.status) { [string]$parsed.status } elseif ($process.ExitCode -eq 0) { 'completed' } else { 'error' }
        $receiptError = if ($killGraceExpired) { $killFailed } elseif ($timedOut) { "agy CLI exceeded hard deadline of $DeadlineSeconds seconds and was terminated." } else { $cliError }
        $succeeded = $status -in @('completed', 'success', 'SUCCESS') -and [string]::IsNullOrWhiteSpace($receiptError)
        return [pscustomobject]@{
            action = $ActionName
            transport = 'agy'
            legacy = $false
            conversationId = $(if ($parsed.conversation_id) { [string]$parsed.conversation_id } elseif ($ConversationId) { $ConversationId } else { '' })
            status = $status
            response = $(if ($parsed.response) { [string]$parsed.response } else { '' })
            error = $receiptError
            failure = $receiptError
            matched = $succeeded
            usable = $succeeded
            timeout = $timedOut
            model = $Model
            exitCode = $(if ($process.HasExited) { $process.ExitCode } else { $null })
            timedOut = $timedOut
            elapsedSeconds = [math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
            workspacePath = $resolvedWorkspacePath
            projectId = $(if ($Project) { [string]$Project.Id } else { '' })
            projectSource = $(if ($Project) { [string]$Project.Source } else { '' })
            projectBindingRequested = [bool]($Project -and -not [string]::IsNullOrWhiteSpace([string]$Project.Id))
            uiProjectVisibility = 'not_verified'
            uiNote = 'Antigravity 2.4.3 may label agy SQLite conversations Outside of Project even when agy logs confirm the project id.'
            resumeCommand = $(if ($ActionName -eq 'start' -and $parsed.conversation_id) { "Invoke-AntigravityBridge.ps1 -Action send -ConversationId '$([string]$parsed.conversation_id)' -WorkspacePath '$resolvedWorkspacePath'" } else { '' })
        }
    } finally {
        $stopwatch.Stop()
        if ($process) { $process.Dispose() }
    }
}

function Invoke-VisibleRpcPrompt {
    param([string]$Prompt,[string]$ActionName,[string]$CascadeId='',[string]$Model='',[string]$WorkspacePath='',[datetime]$DeadlineUtc,[switch]$OmitRequestedModel,[string]$RequestId='',[string]$MissionId='',[string]$LaneId='')
    . "$PSScriptRoot\Invoke-AntigravityRpc.ps1"
    $watch=[Diagnostics.Stopwatch]::StartNew(); $id=$CascadeId; $sendStarted=$false
    try {
        $session=Get-AntigravitySessionInfo
        if([string]::IsNullOrWhiteSpace($id)){$cascade=New-AntigravityCascade -Model $Model -WorkspacePaths @($WorkspacePath) -DeadlineUtc $DeadlineUtc -Session $session;$id=[string]$cascade.CascadeId}
        $marker = "ANTIGRAVITY_BRIDGE_MARKER_$([guid]::NewGuid().ToString('N'))"
        $markedPrompt = "$Prompt`n`nPlease finish your reply with this exact marker on its own line: $marker"
        $sendStarted=$true
        Send-AntigravityMessage -CascadeId $id -Text $markedPrompt -Model $Model -OmitRequestedModel:$OmitRequestedModel -DeadlineUtc $DeadlineUtc -Session $session | Out-Null
        $outcome = Wait-AntigravityTrajectoryMatchResult -CascadeId $id -Pattern ([regex]::Escape($marker)) -DeadlineUtc $DeadlineUtc -Session $session
        $receiptError=[string]$outcome.failure;$status=if($outcome.matched){'completed'}elseif($outcome.timedOut){'timeout'}else{'error'}
        return [pscustomobject]@{action=$ActionName;transport='rpc';private=$true;legacy=$false;cascadeId=$id;conversationId=$id;status=$status;response=[string]$outcome.response;error=$receiptError;failure=$receiptError;matched=[bool]$outcome.matched;usable=[bool]$outcome.matched;timeout=[bool]$outcome.timedOut;timedOut=[bool]$outcome.timedOut;model=(Resolve-AntigravityModelSelection -Model $Model).ModelId;elapsedSeconds=[math]::Round($watch.Elapsed.TotalSeconds,3);workspacePath=(Resolve-Path -LiteralPath $WorkspacePath).Path;visibility=$(if($outcome.matched){'hub_visible'}else{'not_verified'});visibilityEvidence=$(if($outcome.matched){'native cascade indexed by Antigravity Hub; project classification is controlled by Antigravity'}else{'RPC cascade did not complete'});delivery_state=$(if($outcome.timedOut){'DELIVERY_UNKNOWN'}elseif($outcome.matched){'DELIVERED'}else{'ACCEPTED_PENDING'});safe_to_fallback=$false;fallbackUsed=$false;fallbackContinuation='same_cascade';requestId=$RequestId;missionId=$MissionId;laneId=$LaneId;attemptedTransports=@('rpc');resumeCommand="Invoke-AntigravityBridge.ps1 -Action send -Transport rpc -CascadeId '$id' -WorkspacePath '$(Resolve-Path -LiteralPath $WorkspacePath)'"}}
    catch {return [pscustomobject]@{action=$ActionName;transport='rpc';private=$true;legacy=$false;cascadeId=$id;conversationId=$id;status='error';response='';error=$_.Exception.Message;failure=$_.Exception.Message;matched=$false;usable=$false;timeout=$false;timedOut=$false;model=$Model;elapsedSeconds=[math]::Round($watch.Elapsed.TotalSeconds,3);workspacePath=$WorkspacePath;visibility='not_verified';visibilityEvidence='RPC attempt did not complete';delivery_state=$(if($sendStarted){'DELIVERY_UNKNOWN'}else{'PRE_DISPATCH_FAILED'});safe_to_fallback=(-not $sendStarted);fallbackUsed=$false;fallbackContinuation=$(if($sendStarted){'resume_same_cascade'}else{'not_started'});requestId=$RequestId;missionId=$MissionId;laneId=$LaneId;attemptedTransports=@('rpc');resumeCommand=''}}
    finally {$watch.Stop()}
}
function Invoke-LegacyRpcAction {
    param([string]$ActionName)
    . "$PSScriptRoot\Invoke-AntigravityRpc.ps1"
    switch ($ActionName) {
        'discover' { return (ConvertTo-AntigravitySessionPublicInfo -Session (Get-AntigravitySessionInfo) -ShowSecret:$ShowSecret) }
        'trajectory' {
            if ([string]::IsNullOrWhiteSpace($CascadeId)) { throw "Action 'trajectory' requires -CascadeId" }
            return (Get-AntigravityTrajectory -CascadeId $CascadeId -Verbosity $Verbosity -Session (Get-AntigravitySessionInfo))
        }
        default { throw "Action '$ActionName' has no legacy RPC implementation in this wrapper." }
    }
}

if ($Action -in @('discover', 'trajectory')) {
    $result = Invoke-LegacyRpcAction -ActionName $Action
    [pscustomobject]@{ action = $Action; transport = 'rpc'; legacy = $true; diagnostic = $true; result = $result } | ConvertTo-Json -Depth 10
    return
}

if ($Action -eq 'matrix') {
    if ($Transport -ne 'rpc') { throw 'Action matrix is an RPC-only diagnostic. Re-run with -Transport rpc; it is not an official agy conversation flow.' }
    if ($DryRun) { & "$PSScriptRoot\Run-AntigravityCapabilityMatrix.ps1" -WorkspacePath $WorkspacePath -Model $Model -DryRun } else { & "$PSScriptRoot\Run-AntigravityCapabilityMatrix.ps1" -WorkspacePath $WorkspacePath -Model $Model }
    return
}

$prompt = switch ($Action) {
    'start' {
        if ([string]::IsNullOrWhiteSpace($OpeningPrompt)) { throw "Action 'start' requires -OpeningPrompt" }
        if ($NoIntro) { $OpeningPrompt } else { (Get-ConversationIntro -Style $IntroStyle) + "`n`n" + $OpeningPrompt }
    }
    'send' {
        if ([string]::IsNullOrWhiteSpace($ConversationId) -and [string]::IsNullOrWhiteSpace($CascadeId)) { throw "Action 'send' requires -ConversationId (or legacy alias -CascadeId)" }
        if ([string]::IsNullOrWhiteSpace($Text)) { throw "Action 'send' requires -Text" }
        $Text
    }
    'smoke' {
        if (-not [string]::IsNullOrWhiteSpace($Text)) { $Text } elseif (-not [string]::IsNullOrWhiteSpace($OpeningPrompt)) { $OpeningPrompt } else { 'Reply only AGY_BRIDGE_OK.' }
    }
}

$effectiveTimeout = if ($Action -eq 'smoke') { [Math]::Min($TimeoutSeconds, 30) } else { $TimeoutSeconds }
$deadlineUtc = [datetime]::UtcNow.AddSeconds($effectiveTimeout)
$project = if ($Action -in @('start', 'smoke')) { Resolve-AgyProject -WorkspacePath $WorkspacePath -ExplicitProjectId $ProjectId } else { [pscustomobject]@{ Id = ''; Source = 'conversation' } }

$rpcAttempt = $null
if ($Transport -in @('auto', 'rpc')) {
    $rpcCascadeId = if ($CascadeId) { $CascadeId } elseif ($Action -eq 'send') { $ConversationId } else { '' }
    $rpcAttempt = Invoke-VisibleRpcPrompt -Prompt $prompt -ActionName $Action -CascadeId $rpcCascadeId -Model $Model -WorkspacePath $WorkspacePath -DeadlineUtc $deadlineUtc -OmitRequestedModel:$OmitRequestedModel -RequestId $RequestId -MissionId $MissionId -LaneId $LaneId
    Add-AgyTranscript -Receipt $rpcAttempt -Prompt $prompt -WorkspacePath $WorkspacePath -TranscriptDirectory $TranscriptDirectory -Disabled:$NoTranscript
    if ($Transport -eq 'rpc' -or $rpcAttempt.usable -or -not $rpcAttempt.safe_to_fallback) {
        $rpcAttempt | ConvertTo-Json -Depth 8
        if ($rpcAttempt.status -eq 'timeout' -and $AllowTimeout) { exit 0 }
        if (-not $rpcAttempt.usable) { exit 1 }
        exit 0
    }
}

$receipt = Invoke-AgyPrompt -Prompt $prompt -ConversationId $(if ($Transport -eq 'agy' -and $Action -eq 'send') { if ($ConversationId) { $ConversationId } else { $CascadeId } } else { '' }) -Model (Resolve-AgyModel -RequestedModel $Model) -Executable (Resolve-AgyExecutable -Path $AgyPath) -DeadlineSeconds ([math]::Max(1, [math]::Floor(($deadlineUtc - [datetime]::UtcNow).TotalSeconds))) -WorkspacePath $WorkspacePath -ActionName $Action -Project $project
$receipt | Add-Member -NotePropertyName requestId -NotePropertyValue $RequestId -Force; $receipt | Add-Member -NotePropertyName missionId -NotePropertyValue $MissionId -Force; $receipt | Add-Member -NotePropertyName laneId -NotePropertyValue $LaneId -Force
if ($rpcAttempt) { $receipt | Add-Member -NotePropertyName fallbackUsed -NotePropertyValue $true -Force; $receipt | Add-Member -NotePropertyName attemptedTransports -NotePropertyValue @('rpc', 'agy') -Force; $receipt | Add-Member -NotePropertyName rpcCascadeId -NotePropertyValue $rpcAttempt.cascadeId -Force; $receipt | Add-Member -NotePropertyName rpcFailure -NotePropertyValue $rpcAttempt.failure -Force; $receipt | Add-Member -NotePropertyName fallbackContinuation -NotePropertyValue $(if ($Action -eq 'send') { 'new_conversation' } else { 'native_agy' }) -Force }
Add-AgyTranscript -Receipt $receipt -Prompt $prompt -WorkspacePath $WorkspacePath -TranscriptDirectory $TranscriptDirectory -Disabled:$NoTranscript
$receipt | ConvertTo-Json -Depth 6

# JSON is emitted before the process status so callers can retain a diagnostic receipt.
# Only an explicitly allowed timeout is considered inspectable-success; all other
# non-completed outcomes preserve PowerShell's non-zero CLI semantics.
if ($receipt.status -eq 'timeout' -and $AllowTimeout) {
    exit 0
}
if (-not $receipt.usable -or -not [string]::IsNullOrWhiteSpace([string]$receipt.error)) {
    exit 1
}
exit 0
