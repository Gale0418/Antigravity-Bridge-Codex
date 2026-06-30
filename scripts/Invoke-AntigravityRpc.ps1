$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\Discover-AntigravitySession.ps1"

function Get-AntigravityServiceUri {
    param(
        [Parameter(Mandatory = $true)]
        [int]$HttpPort,

        [Parameter(Mandatory = $true)]
        [string]$Method
    )

    return "http://127.0.0.1:$HttpPort/exa.language_server_pb.LanguageServerService/$Method"
}

function Resolve-AntigravityModel {
    param(
        [string]$Model,
        [string]$ConversationDirectory = ''
    )

    return (Resolve-AntigravityModelSelection -Model $Model -ConversationDirectory $ConversationDirectory).ModelId
}

function Get-AntigravityConversationDirectoryCandidates {
    param(
        [string]$Platform = '',
        [string]$HomeDirectory = '',
        [string]$UserProfileDirectory = ''
    )

    $resolvedPlatform = if ([string]::IsNullOrWhiteSpace($Platform)) {
        Get-AntigravityPlatform
    }
    else {
        $Platform
    }

    $resolvedHome = if (-not [string]::IsNullOrWhiteSpace($HomeDirectory)) {
        $HomeDirectory
    }
    elseif (-not [string]::IsNullOrWhiteSpace($UserProfileDirectory)) {
        $UserProfileDirectory
    }
    else {
        [Environment]::GetFolderPath('UserProfile')
    }

    $candidates = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($resolvedHome)) {
        $candidates.Add((Join-Path $resolvedHome '.gemini/antigravity/conversations'))
    }

    if ($resolvedPlatform -eq 'Windows' -and -not [string]::IsNullOrWhiteSpace($resolvedHome)) {
        $candidates.Add((Join-Path $resolvedHome '.gemini\antigravity\conversations'))
    }

    return @($candidates | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
}

function ConvertFrom-AntigravityBinaryAscii {
    param(
        [Parameter(Mandatory = $true)]
        [byte[]]$Bytes
    )

    $builder = [System.Text.StringBuilder]::new($Bytes.Length)
    foreach ($byte in $Bytes) {
        if (($byte -ge 32 -and $byte -le 126) -or $byte -in @(9, 10, 13)) {
            [void]$builder.Append([char]$byte)
        }
        else {
            [void]$builder.Append(' ')
        }
    }

    return $builder.ToString()
}

function New-AntigravityModelSelection {
    param(
        [string]$ModelId = '',
        [string]$ModelEnum = ''
    )

    return [pscustomobject]@{
        ModelId = $ModelId
        ModelEnum = $ModelEnum
    }
}

function Find-AntigravityRecentModelSelection {
    param(
        [string]$ConversationDirectory = '',
        [string]$Platform = '',
        [string]$HomeDirectory = '',
        [string]$UserProfileDirectory = '',
        [int]$MaxFiles = 8
    )

    $directories = if (-not [string]::IsNullOrWhiteSpace($ConversationDirectory)) {
        @($ConversationDirectory)
    }
    else {
        Get-AntigravityConversationDirectoryCandidates -Platform $Platform -HomeDirectory $HomeDirectory -UserProfileDirectory $UserProfileDirectory
    }

    $modelPattern = [regex]'(?<![A-Za-z0-9])(?:gemini|claude|gpt|gemma|openrouter)(?:[a-z0-9./:-]*[a-z0-9])'
    $enumPattern = [regex]'MODEL_PLACEHOLDER_M\d+'

    foreach ($directory in $directories) {
        if (-not (Test-Path -LiteralPath $directory)) {
            continue
        }

        $files = @(Get-ChildItem -LiteralPath $directory -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in @('.db', '.pb') } |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First $MaxFiles)

        foreach ($file in $files) {
            try {
                $content = ConvertFrom-AntigravityBinaryAscii -Bytes ([System.IO.File]::ReadAllBytes($file.FullName))
            }
            catch {
                continue
            }

            $compositeMatch = [regex]::Match(
                $content,
                '(?s)(?<model>(?<![A-Za-z0-9])(?:gemini|claude|gpt|gemma|openrouter)(?:[a-z0-9./:-]*[a-z0-9])).{0,220}?model_enum\s+(?<enum>MODEL_PLACEHOLDER_M\d+)'
            )
            if ($compositeMatch.Success) {
                return (New-AntigravityModelSelection -ModelId $compositeMatch.Groups['model'].Value.Trim() -ModelEnum $compositeMatch.Groups['enum'].Value.Trim())
            }

            foreach ($match in $modelPattern.Matches($content)) {
                $candidate = $match.Value.Trim()
                if ($candidate -notmatch '[-/:]') {
                    continue
                }
                $windowStart = [Math]::Max(0, $match.Index - 220)
                $windowLength = [Math]::Min($content.Length - $windowStart, 440)
                $window = $content.Substring($windowStart, $windowLength)
                $enumMatch = $enumPattern.Match($window)
                if ($enumMatch.Success) {
                    return (New-AntigravityModelSelection -ModelId $candidate -ModelEnum $enumMatch.Value.Trim())
                }

                return (New-AntigravityModelSelection -ModelId $candidate)
            }
        }
    }

    return (New-AntigravityModelSelection)
}

function Find-AntigravityRecentModel {
    param(
        [string]$ConversationDirectory = '',
        [string]$Platform = '',
        [string]$HomeDirectory = '',
        [string]$UserProfileDirectory = '',
        [int]$MaxFiles = 8
    )

    return (Find-AntigravityRecentModelSelection -ConversationDirectory $ConversationDirectory -Platform $Platform -HomeDirectory $HomeDirectory -UserProfileDirectory $UserProfileDirectory -MaxFiles $MaxFiles).ModelId
}

function Resolve-AntigravityModelSelection {
    param(
        [string]$Model = '',
        [string]$ConversationDirectory = ''
    )

    $explicitModel = ''
    if (-not [string]::IsNullOrWhiteSpace($Model)) {
        $explicitModel = $Model.Trim()
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:ANTIGRAVITY_MODEL)) {
        $explicitModel = $env:ANTIGRAVITY_MODEL.Trim()
    }

    $recentSelection = Find-AntigravityRecentModelSelection -ConversationDirectory $ConversationDirectory

    if (-not [string]::IsNullOrWhiteSpace($explicitModel)) {
        if ($explicitModel -match '^MODEL_PLACEHOLDER_M\d+$') {
            return (New-AntigravityModelSelection -ModelId $(if ($recentSelection.ModelEnum -eq $explicitModel) { $recentSelection.ModelId } else { $explicitModel }) -ModelEnum $explicitModel)
        }

        if ($recentSelection.ModelId -eq $explicitModel -and -not [string]::IsNullOrWhiteSpace($recentSelection.ModelEnum)) {
            return $recentSelection
        }

        return (New-AntigravityModelSelection -ModelId $explicitModel)
    }

    if (-not [string]::IsNullOrWhiteSpace($recentSelection.ModelId)) {
        return $recentSelection
    }

    throw 'Antigravity model is required. Pass -Model, set $env:ANTIGRAVITY_MODEL, or ensure Antigravity has a recent successful local conversation with a real model id.'
}

function ConvertTo-AntigravityFileUri {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ($Path -match '^[\\/]{2}[^\\/]') {
        throw "UNC paths are currently not supported: $Path"
    }

    if ($Path -match '^[A-Za-z]:[\\/]') {
        $normalizedWindowsPath = $Path.Replace('\', '/')
        return [System.Uri]::new($normalizedWindowsPath).AbsoluteUri
    }

    $resolved = [System.IO.Path]::GetFullPath($Path)
    if ($resolved -match '^[\\/]{2}[^\\/]') {
        throw "UNC paths are currently not supported: $resolved"
    }
    if ($resolved -match '^[A-Za-z]:[\\/]') {
        return [System.Uri]::new($resolved).AbsoluteUri
    }
    elseif ($resolved -match '^/') {
        return [System.Uri]::new($resolved).AbsoluteUri
    }

    throw "Only Windows drive-letter and POSIX absolute paths are currently supported: $resolved"
}

function Get-AntigravityHeaders {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Session
    )

    return @{
        'x-codeium-csrf-token' = $Session.CsrfToken
        'Content-Type' = 'application/json'
    }
}

function Invoke-AntigravityRpc {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [hashtable]$Body,

        [psobject]$Session = (Get-AntigravitySessionInfo)
    )

    $uri = Get-AntigravityServiceUri -HttpPort $Session.HttpPort -Method $Method
    $headers = Get-AntigravityHeaders -Session $Session
    $jsonBody = $Body | ConvertTo-Json -Depth 20

    return Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -Body $jsonBody
}

function New-AntigravityCascade {
    param(
        [string]$Model = '',
        [string[]]$WorkspacePaths,
        [string]$CascadeId = ([guid]::NewGuid().Guid),
        [psobject]$Session = (Get-AntigravitySessionInfo)
    )

    $resolvedModel = Resolve-AntigravityModelSelection -Model $Model
    $body = @{
        source = 1
        cascadeId = $CascadeId
        requestedModel = $(if ($resolvedModel.ModelEnum) { $resolvedModel.ModelEnum } else { $resolvedModel.ModelId })
    }

    if ($WorkspacePaths) {
        $body.workspaceUris = @($WorkspacePaths | ForEach-Object { ConvertTo-AntigravityFileUri -Path $_ })
    }

    $response = Invoke-AntigravityRpc -Method 'StartCascade' -Body $body -Session $Session

    return [pscustomobject]@{
        CascadeId = $(if ($response.cascadeId) { $response.cascadeId } else { $CascadeId })
        Session = $Session
        WorkspaceUris = $body.workspaceUris
        Response = $response
    }
}

function Send-AntigravityMessage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CascadeId,

        [Parameter(Mandatory = $true)]
        [string]$Text,

        [string]$Model = '',
        [switch]$OmitRequestedModel,
        [psobject]$Session = (Get-AntigravitySessionInfo)
    )

    $body = @{
        cascadeId = $CascadeId
        items = @(
            @{
                text = $Text
            }
        )
    }

    if (-not $OmitRequestedModel) {
        $resolvedModel = Resolve-AntigravityModelSelection -Model $Model
        $body.cascadeConfig = @{
            plannerConfig = @{
                $(if ($resolvedModel.ModelEnum) {
                    'planModel'
                } else {
                    'requestedModel'
                }) = $(if ($resolvedModel.ModelEnum) {
                    $resolvedModel.ModelEnum
                } else {
                    @{
                        model = $resolvedModel.ModelId
                    }
                })
            }
        }
    }

    return Invoke-AntigravityRpc -Method 'SendUserCascadeMessage' -Body $body -Session $Session
}

function Get-AntigravityTrajectoryEnvelope {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CascadeId,

        [int]$Verbosity = 2,
        [psobject]$Session = (Get-AntigravitySessionInfo)
    )

    return Invoke-AntigravityRpc -Method 'GetCascadeTrajectory' -Body @{
        cascadeId = $CascadeId
        verbosity = $Verbosity
    } -Session $Session
}

function Get-AntigravityTrajectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CascadeId,

        [int]$Verbosity = 2,
        [psobject]$Session = (Get-AntigravitySessionInfo)
    )

    $envelope = Get-AntigravityTrajectoryEnvelope -CascadeId $CascadeId -Verbosity $Verbosity -Session $Session
    return $envelope.trajectory
}

function Get-AntigravityTrajectorySteps {
    param([psobject]$Trajectory)

    if ($null -eq $Trajectory -or $null -eq $Trajectory.steps) {
        return @()
    }

    return @($Trajectory.steps)
}

function Get-LatestAntigravityPlannerResponseText {
    param([psobject]$Trajectory)

    $step = Get-AntigravityTrajectorySteps -Trajectory $Trajectory |
        Where-Object { $_.type -eq 'CORTEX_STEP_TYPE_PLANNER_RESPONSE' } |
        Select-Object -Last 1

    if ($null -eq $step) {
        return ''
    }

    return [string]$step.plannerResponse.response
}

function Get-LatestAntigravityErrorText {
    param([psobject]$Trajectory)

    $step = Get-AntigravityTrajectorySteps -Trajectory $Trajectory |
        Where-Object { $_.type -eq 'CORTEX_STEP_TYPE_ERROR_MESSAGE' } |
        Select-Object -Last 1

    if ($null -eq $step) {
        return ''
    }

    return [string]$(
        if ($step.errorMessage.error.shortError) {
            $step.errorMessage.error.shortError
        } elseif ($step.errorMessage.error.userErrorMessage) {
            $step.errorMessage.error.userErrorMessage
        } else {
            $step.errorMessage | ConvertTo-Json -Depth 8 -Compress
        }
    )
}

function Wait-AntigravityTrajectoryOutcome {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CascadeId,

        [Parameter(Mandatory = $true)]
        [string]$Pattern,

        [int]$TimeoutSeconds = 90,
        [int]$PollIntervalSeconds = 3,
        [psobject]$Session = (Get-AntigravitySessionInfo)
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastTrajectory = $null
    $lastResponse = ''
    $lastError = ''
    $lastCombined = ''

    do {
        $lastTrajectory = Get-AntigravityTrajectory -CascadeId $CascadeId -Session $Session
        $lastResponse = Get-LatestAntigravityPlannerResponseText -Trajectory $lastTrajectory
        $lastError = Get-LatestAntigravityErrorText -Trajectory $lastTrajectory
        $lastCombined = @($lastResponse, $lastError) -join "`n"

        if ($lastCombined -match $Pattern) {
            return [pscustomobject]@{
                CascadeId = $CascadeId
                Pattern = $Pattern
                Matched = $true
                TimedOut = $false
                Trajectory = $lastTrajectory
                Response = $lastResponse
                Failure = $lastError
                ObservedText = $lastCombined
            }
        }

        if ((Get-Date) -ge $deadline) {
            break
        }

        Start-Sleep -Seconds $PollIntervalSeconds
    } while ($true)

    return [pscustomobject]@{
        CascadeId = $CascadeId
        Pattern = $Pattern
        Matched = $false
        TimedOut = $true
        Trajectory = $lastTrajectory
        Response = $lastResponse
        Failure = $lastError
        ObservedText = $lastCombined
    }
}

function Wait-AntigravityTrajectoryMatch {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CascadeId,

        [Parameter(Mandatory = $true)]
        [string]$Pattern,

        [int]$TimeoutSeconds = 90,
        [int]$PollIntervalSeconds = 3,
        [psobject]$Session = (Get-AntigravitySessionInfo)
    )

    $outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $CascadeId -Pattern $Pattern -TimeoutSeconds $TimeoutSeconds -PollIntervalSeconds $PollIntervalSeconds -Session $Session
    if ($outcome.Matched) {
        return $outcome.Trajectory
    }

    throw "Timed out waiting for pattern $Pattern in cascade $CascadeId"
}
