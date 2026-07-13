param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('discover', 'matrix', 'start', 'send', 'smoke', 'trajectory')]
    [string]$Action,

    [string]$WorkspacePath = (Get-Location).Path,
    [string]$Model = '',

    # Specific to matrix
    [switch]$DryRun,

    # Specific to start / send
    [string]$OpeningPrompt,
    [ValidateSet('cute','professional')]
    [string]$IntroStyle = 'cute',
    [switch]$NoIntro,
    [string]$WaitPattern = '',
    [string]$Text,
    [switch]$AllowTimeout,
    [switch]$OmitRequestedModel,
    [string]$CascadeId,

    # Specific to trajectory
    [int]$Verbosity = 2,
    [switch]$ShowSecret
)

$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\Invoke-AntigravityRpc.ps1"

function Get-ConversationIntro {
    param([string]$Style)
    if ($Style -eq 'professional') {
        return '我是 Codex，負責規劃、整理和驗收；你負責在 Antigravity 這邊幫忙執行或一起想辦法。接下來請和我協作完成同一個任務，資訊不足就直接提醒我。'
    }
    return '我是 Codex，今天一起來幫主人做事的搭檔。我負責規劃、整理和驗收，你負責在 Antigravity 這邊幫忙執行或一起想辦法；我們像家人聊天一樣合作就好，資訊不夠就直接提醒我。'
}

function New-AntigravityCompletionMarker {
    return "ANTIGRAVITY_BRIDGE_MARKER_$([guid]::NewGuid().ToString('N'))"
}

function Add-AntigravityCompletionMarkerInstruction {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$Marker
    )

    return "$Text`n`nPlease finish your reply with this exact marker on its own line: $Marker"
}

function Resolve-AntigravityWaitPattern {
    param(
        [string]$WaitPattern,

        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    if (-not [string]::IsNullOrWhiteSpace($WaitPattern)) {
        return [pscustomobject]@{
            Pattern = $WaitPattern
            Text = $Text
            Marker = ''
        }
    }

    $marker = New-AntigravityCompletionMarker
    return [pscustomobject]@{
        Pattern = $marker
        Text = Add-AntigravityCompletionMarkerInstruction -Text $Text -Marker $marker
        Marker = $marker
    }
}

function Assert-AntigravityTimeoutOutcome {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Outcome,

        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    if (-not [string]::IsNullOrWhiteSpace([string]$Outcome.Failure)) {
        throw "Action '$Action' failed in cascade $($Outcome.CascadeId): $($Outcome.Failure)"
    }

    if ($Outcome.TimedOut) {
        throw "Action '$Action' timed out waiting for pattern $($Outcome.Pattern) in cascade $($Outcome.CascadeId). Re-run with -AllowTimeout to inspect partial output."
    }
}

switch ($Action) {
    'discover' {
        $session = Get-AntigravitySessionInfo
        ConvertTo-AntigravitySessionPublicInfo -Session $session -ShowSecret:$ShowSecret | ConvertTo-Json -Depth 5
    }
    'matrix' {
        if ($DryRun) {
            & "$PSScriptRoot\Run-AntigravityCapabilityMatrix.ps1" -WorkspacePath $WorkspacePath -Model $Model -DryRun
        } else {
            & "$PSScriptRoot\Run-AntigravityCapabilityMatrix.ps1" -WorkspacePath $WorkspacePath -Model $Model
        }
    }
    'start' {
        if ([string]::IsNullOrWhiteSpace($OpeningPrompt)) {
            throw "Action 'start' requires -OpeningPrompt"
        }
        $resolvedWorkspacePath = (Resolve-Path -LiteralPath $WorkspacePath).Path
        $session = Get-AntigravitySessionInfo
        $cascade = New-AntigravityCascade -Model $Model -WorkspacePaths @($resolvedWorkspacePath) -Session $session

        $message = if ($NoIntro) {
            $OpeningPrompt
        } else {
            (Get-ConversationIntro -Style $IntroStyle) + "`n`n" + $OpeningPrompt
        }

        $wait = Resolve-AntigravityWaitPattern -WaitPattern $WaitPattern -Text $message

        Send-AntigravityMessage -CascadeId $cascade.CascadeId -Text $wait.Text -Model $Model -Session $session | Out-Null
        $trajectoryOutcome = Wait-AntigravityTrajectoryMatchResult -CascadeId $cascade.CascadeId -Pattern $wait.Pattern -TimeoutSeconds 90 -Session $session
        if (-not $AllowTimeout -or -not [string]::IsNullOrWhiteSpace([string]$trajectoryOutcome.Failure)) {
            Assert-AntigravityTimeoutOutcome -Outcome $trajectoryOutcome -Action 'start'
        }
        $response = $trajectoryOutcome.Response
        $failure = $trajectoryOutcome.Failure

        [pscustomobject]@{
            action = 'start'
            cascadeId = $cascade.CascadeId
            workspacePath = $resolvedWorkspacePath
            introStyle = $(if ($NoIntro) { 'none' } else { $IntroStyle })
            matched = $trajectoryOutcome.Matched
            timeout = $trajectoryOutcome.TimedOut
            response = $response
            failure = $failure
            elapsedSeconds = $trajectoryOutcome.ElapsedSeconds
        } | ConvertTo-Json -Depth 6
    }
    'send' {
        if ([string]::IsNullOrWhiteSpace($CascadeId)) {
            throw "Action 'send' requires -CascadeId"
        }
        if ([string]::IsNullOrWhiteSpace($Text)) {
            throw "Action 'send' requires -Text"
        }
        $session = Get-AntigravitySessionInfo
        $wait = Resolve-AntigravityWaitPattern -WaitPattern $WaitPattern -Text $Text
        Send-AntigravityMessage -CascadeId $CascadeId -Text $wait.Text -Model $Model -OmitRequestedModel:$OmitRequestedModel -Session $session | Out-Null
        $trajectoryOutcome = Wait-AntigravityTrajectoryMatchResult -CascadeId $CascadeId -Pattern $wait.Pattern -TimeoutSeconds 90 -Session $session
        if (-not $AllowTimeout -or -not [string]::IsNullOrWhiteSpace([string]$trajectoryOutcome.Failure)) {
            Assert-AntigravityTimeoutOutcome -Outcome $trajectoryOutcome -Action 'send'
        }
        $response = $trajectoryOutcome.Response
        $failure = $trajectoryOutcome.Failure

        [pscustomobject]@{
            action = 'send'
            cascadeId = $CascadeId
            matched = $trajectoryOutcome.Matched
            timeout = $trajectoryOutcome.TimedOut
            response = $response
            failure = $failure
            elapsedSeconds = $trajectoryOutcome.ElapsedSeconds
        } | ConvertTo-Json -Depth 6
    }
    'smoke' {
        $resolvedWorkspacePath = (Resolve-Path -LiteralPath $WorkspacePath).Path
        $session = Get-AntigravitySessionInfo
        $cascade = New-AntigravityCascade -Model $Model -WorkspacePaths @($resolvedWorkspacePath) -Session $session
        $marker = New-AntigravityCompletionMarker
        $smokePrompt = if (-not [string]::IsNullOrWhiteSpace($Text)) { $Text } else { $OpeningPrompt }
        $smokeText = if ([string]::IsNullOrWhiteSpace($smokePrompt)) {
            "Please reply with this exact marker on its own line: $marker"
        } else {
            Add-AntigravityCompletionMarkerInstruction -Text $smokePrompt -Marker $marker
        }

        Send-AntigravityMessage -CascadeId $cascade.CascadeId -Text $smokeText -Model $Model -OmitRequestedModel:$OmitRequestedModel -Session $session | Out-Null
        # Smoke is intentionally bounded and deterministic: one marker, one
        # 30-second wait.  It is a health check, not an open-ended chat call.
        $trajectoryOutcome = Wait-AntigravityTrajectoryMatchResult -CascadeId $cascade.CascadeId -Pattern $marker -TimeoutSeconds 30 -Session $session
        if (-not $AllowTimeout -or -not [string]::IsNullOrWhiteSpace([string]$trajectoryOutcome.Failure)) {
            Assert-AntigravityTimeoutOutcome -Outcome $trajectoryOutcome -Action 'smoke'
        }

        [pscustomobject]@{
            action = 'smoke'
            cascadeId = $cascade.CascadeId
            workspacePath = $resolvedWorkspacePath
            marker = $marker
            matched = $trajectoryOutcome.Matched
            timeout = $trajectoryOutcome.TimedOut
            response = $trajectoryOutcome.Response
            failure = $trajectoryOutcome.Failure
            elapsedSeconds = $trajectoryOutcome.ElapsedSeconds
        } | ConvertTo-Json -Depth 6
    }
    'trajectory' {
        if ([string]::IsNullOrWhiteSpace($CascadeId)) {
            throw "Action 'trajectory' requires -CascadeId"
        }
        $session = Get-AntigravitySessionInfo
        $traj = Get-AntigravityTrajectory -CascadeId $CascadeId -Verbosity $Verbosity -Session $session
        $traj | ConvertTo-Json -Depth 10 -Compress
    }
}
