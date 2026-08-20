param(
    [string]$WorkspacePath = (Get-Location).Path,
    [Parameter(Mandatory = $true)]
    [string]$OpeningPrompt,
    [string]$Model = '',
    [ValidateSet('cute', 'professional')]
    [string]$IntroStyle = 'cute',
    [switch]$NoIntro,
    [ValidateSet('auto', 'agy', 'rpc')]
    [string]$Transport = 'auto',
    [string]$AgyPath = '',
    [ValidateRange(1, 1800)]
    [int]$TimeoutSeconds = 90,
    [string]$RequestId = '',
    [string]$MissionId = '',
    [string]$LaneId = ''
)

$ErrorActionPreference = 'Stop'

# Auto prefers a Hub-native visible RPC conversation and falls back to agy.
& "$PSScriptRoot\Invoke-AntigravityBridge.ps1" -Action start -WorkspacePath $WorkspacePath -OpeningPrompt $OpeningPrompt -Model $Model -IntroStyle $IntroStyle -NoIntro:$NoIntro -Transport $Transport -AgyPath $AgyPath -TimeoutSeconds $TimeoutSeconds -RequestId $RequestId -MissionId $MissionId -LaneId $LaneId
exit $LASTEXITCODE
