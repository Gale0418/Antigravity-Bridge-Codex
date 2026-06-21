param(
    [string]$WorkspacePath = (Get-Location).Path,
    [Parameter(Mandatory = $true)]
    [string]$OpeningPrompt,
    [string]$Model = 'MODEL_PLACEHOLDER_M36',
    [ValidateSet('cute','professional')]
    [string]$IntroStyle = 'cute',
    [switch]$NoIntro,
    [string]$WaitPattern = '(?s).+'
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

$resolvedWorkspacePath = (Resolve-Path -LiteralPath $WorkspacePath).Path
$session = Get-AntigravitySessionInfo
$cascade = New-AntigravityCascade -Model $Model -WorkspacePaths @($resolvedWorkspacePath) -Session $session

$message = if ($NoIntro) {
    $OpeningPrompt
} else {
    (Get-ConversationIntro -Style $IntroStyle) + "`n`n" + $OpeningPrompt
}

Send-AntigravityMessage -CascadeId $cascade.CascadeId -Text $message -Model $Model -Session $session | Out-Null
$trajectory = Wait-AntigravityTrajectoryMatch -CascadeId $cascade.CascadeId -Pattern $WaitPattern -TimeoutSeconds 90 -Session $session
$response = Get-LatestAntigravityPlannerResponseText -Trajectory $trajectory
$failure = Get-LatestAntigravityErrorText -Trajectory $trajectory

[pscustomobject]@{
    cascadeId = $cascade.CascadeId
    workspacePath = $resolvedWorkspacePath
    introStyle = $(if ($NoIntro) { 'none' } else { $IntroStyle })
    response = $response
    failure = $failure
} | ConvertTo-Json -Depth 6
