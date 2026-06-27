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

function ConvertTo-AntigravityFileUri {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $resolved = [System.IO.Path]::GetFullPath($Path)
    return [System.Uri]::new($resolved).AbsoluteUri
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
        [string]$Model = 'MODEL_PLACEHOLDER_M36',
        [string[]]$WorkspacePaths,
        [string]$CascadeId = ([guid]::NewGuid().Guid),
        [psobject]$Session = (Get-AntigravitySessionInfo)
    )

    $body = @{
        source = 1
        cascadeId = $CascadeId
        requestedModel = $Model
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

        [string]$Model = 'MODEL_PLACEHOLDER_M36',
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
        $body.cascadeConfig = @{
            plannerConfig = @{
                requestedModel = @{
                    model = $Model
                }
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
