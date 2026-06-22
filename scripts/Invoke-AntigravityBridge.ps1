param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('discover', 'matrix', 'start', 'send', 'trajectory')]
    [string]$Action,

    [string]$WorkspacePath = (Get-Location).Path,
    [string]$Model = 'MODEL_PLACEHOLDER_M36',

    # Specific to matrix
    [switch]$DryRun,

    # Specific to start / send
    [string]$OpeningPrompt,
    [ValidateSet('cute','professional')]
    [string]$IntroStyle = 'cute',
    [switch]$NoIntro,
    [string]$WaitPattern = '(?s).+',
    [string]$Text,
    [switch]$OmitRequestedModel,
    [string]$CascadeId,

    # Specific to trajectory
    [int]$Verbosity = 2
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

switch ($Action) {
    'discover' {
        Get-AntigravitySessionInfo | ConvertTo-Json -Depth 5
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

        Send-AntigravityMessage -CascadeId $cascade.CascadeId -Text $message -Model $Model -Session $session | Out-Null
        $trajectoryResult = Wait-AntigravityTrajectoryMatch -CascadeId $cascade.CascadeId -Pattern $WaitPattern -TimeoutSeconds 90 -Session $session
        $response = Get-LatestAntigravityPlannerResponseText -Trajectory $trajectoryResult
        $failure = Get-LatestAntigravityErrorText -Trajectory $trajectoryResult

        [pscustomobject]@{
            action = 'start'
            cascadeId = $cascade.CascadeId
            workspacePath = $resolvedWorkspacePath
            introStyle = $(if ($NoIntro) { 'none' } else { $IntroStyle })
            response = $response
            failure = $failure
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
        Send-AntigravityMessage -CascadeId $CascadeId -Text $Text -Model $Model -OmitRequestedModel:$OmitRequestedModel -Session $session | Out-Null
        $trajectoryResult = Wait-AntigravityTrajectoryMatch -CascadeId $CascadeId -Pattern $WaitPattern -TimeoutSeconds 90 -Session $session
        $response = Get-LatestAntigravityPlannerResponseText -Trajectory $trajectoryResult
        $failure = Get-LatestAntigravityErrorText -Trajectory $trajectoryResult

        [pscustomobject]@{
            action = 'send'
            cascadeId = $CascadeId
            response = $response
            failure = $failure
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
