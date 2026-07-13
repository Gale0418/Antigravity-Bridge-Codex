param(
    [string]$WorkspacePath = (Get-Location).Path,
    [string]$Model = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\Invoke-AntigravityRpc.ps1"
$resolvedModel = Resolve-AntigravityModel -Model $Model

function New-Result {
    param(
        [string]$Id,
        [string]$Status,
        [string]$CascadeId,
        [string]$Observed,
        [string]$Response,
        [string]$Failure,
        [string]$ArtifactPath,
        [string]$Classification = '',
        [bool]$Matched = $false,
        [bool]$TimedOut = $false
    )

    return [pscustomobject]@{
        id = $Id
        status = $Status
        classification = $Classification
        cascadeId = $CascadeId
        matched = $Matched
        timeout = $TimedOut
        observed = $Observed
        response = $Response
        failure = $Failure
        artifactPath = $ArtifactPath
    }
}

$resolvedWorkspacePath = (Resolve-Path -LiteralPath $WorkspacePath).Path
$workspaceUri = ConvertTo-AntigravityFileUri -Path $resolvedWorkspacePath
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$writeProbePath = Join-Path $resolvedWorkspacePath "antigravity_matrix_write_$timestamp.md"
$editProbePath = Join-Path $resolvedWorkspacePath "antigravity_matrix_edit_$timestamp.md"
$webProbePath = Join-Path $resolvedWorkspacePath "antigravity_matrix_web_$timestamp.md"
$readProbePath = Join-Path $resolvedWorkspacePath "antigravity_matrix_read_$timestamp.txt"
$readProbeToken = "READ_PROBE_$timestamp"

$tests = @(
    [pscustomobject]@{ id = 'roundtrip-response'; artifactPath = $null }
    [pscustomobject]@{ id = 'workspace-awareness'; artifactPath = $null }
    [pscustomobject]@{ id = 'read-existing-file'; artifactPath = $readProbePath }
    [pscustomobject]@{ id = 'write-new-file'; artifactPath = $writeProbePath }
    [pscustomobject]@{ id = 'modify-existing-file'; artifactPath = $editProbePath }
    [pscustomobject]@{ id = 'multi-turn-memory'; artifactPath = $null }
    [pscustomobject]@{ id = 'web-access-probe'; artifactPath = $webProbePath }
    [pscustomobject]@{ id = 'missing-model-negative-check'; artifactPath = $null }
)

if ($DryRun) {
    [pscustomobject]@{
        workspacePath = $resolvedWorkspacePath
        model = $resolvedModel
        testIds = @($tests.id)
        artifactPaths = @($tests.artifactPath | Where-Object { $_ })
    } | ConvertTo-Json -Depth 5
    return
}

$session = Get-AntigravitySessionInfo
$results = New-Object System.Collections.Generic.List[object]

$smokeOutput = & "$PSScriptRoot\Invoke-AntigravityBridge.ps1" -Action smoke -WorkspacePath $resolvedWorkspacePath -Model $resolvedModel -AllowTimeout
$smokeResult = $smokeOutput | ConvertFrom-Json
if (-not $smokeResult.matched) {
    throw "Antigravity Bridge is not ready: $($smokeResult.failure)"
}

try {
    $sharedCascade = New-AntigravityCascade -Model $resolvedModel -WorkspacePaths @($resolvedWorkspacePath) -Session $session

Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text '請只回覆 MATRIX_OK_001' -Model $resolvedModel -Session $session | Out-Null
$outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern 'MATRIX_OK_001' -TimeoutSeconds 45 -Session $session
$response = $outcome.Response
$failure = $outcome.Failure
$results.Add((New-Result -Id 'roundtrip-response' -Status $(if ($response -match 'MATRIX_OK_001') { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $response -Response $response -Failure $failure -ArtifactPath $null -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

$workspacePattern = [string]::Join('|', @([Regex]::Escape($resolvedWorkspacePath), [Regex]::Escape($workspaceUri)))
Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text "請只回覆你目前可見的 workspace 根目錄路徑，例如 $resolvedWorkspacePath 或 $workspaceUri。" -Model $resolvedModel -Session $session | Out-Null
$outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern $workspacePattern -TimeoutSeconds 45 -Session $session
$response = $outcome.Response
$failure = $outcome.Failure
$workspacePass = ($response -match [Regex]::Escape($resolvedWorkspacePath)) -or ($response -match [Regex]::Escape($workspaceUri))
$results.Add((New-Result -Id 'workspace-awareness' -Status $(if ($workspacePass) { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $response -Response $response -Failure $failure -ArtifactPath $null -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

[System.IO.File]::WriteAllText($readProbePath, "$readProbeToken`nSECOND_LINE`n", [System.Text.UTF8Encoding]::new($false))

Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text "請讀取 $readProbePath，然後只回覆第一個非空白行，不要加任何解釋。" -Model $resolvedModel -Session $session | Out-Null
$outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern $readProbeToken -TimeoutSeconds 60 -Session $session
$response = $outcome.Response
$failure = $outcome.Failure
$readPass = $response -match $readProbeToken
$results.Add((New-Result -Id 'read-existing-file' -Status $(if ($readPass) { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $response -Response $response -Failure $failure -ArtifactPath $readProbePath -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text "請在 $writeProbePath 建立 UTF-8 Markdown 檔案，內容只需要兩行：第一行是 '# Matrix Write Probe'，第二行是 'MATRIX_WRITE_$timestamp'。完成後只回覆 DONE_WRITE_$timestamp。" -Model $resolvedModel -Session $session | Out-Null
$outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern "DONE_WRITE_$timestamp" -TimeoutSeconds 90 -Session $session
$response = $outcome.Response
$failure = $outcome.Failure
$writeContent = if (Test-Path -LiteralPath $writeProbePath) { Get-Content -LiteralPath $writeProbePath -Raw } else { '' }
$writePass = (Test-Path -LiteralPath $writeProbePath) -and ($writeContent -match "MATRIX_WRITE_$timestamp")
$results.Add((New-Result -Id 'write-new-file' -Status $(if ($writePass) { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $writeContent -Response $response -Failure $failure -ArtifactPath $writeProbePath -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

[System.IO.File]::WriteAllText($editProbePath, "# Matrix Edit Probe`nBEFORE_EDIT`n", [System.Text.UTF8Encoding]::new($false))
Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text "請修改既有檔案 $editProbePath：保留原本內容，並在最後新增一行 'AFTER_EDIT_$timestamp'。完成後只回覆 DONE_EDIT_$timestamp。" -Model $resolvedModel -Session $session | Out-Null
$outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern "DONE_EDIT_$timestamp" -TimeoutSeconds 90 -Session $session
$response = $outcome.Response
$failure = $outcome.Failure
$editContent = if (Test-Path -LiteralPath $editProbePath) { Get-Content -LiteralPath $editProbePath -Raw } else { '' }
$editPass = ($editContent -match 'BEFORE_EDIT') -and ($editContent -match "AFTER_EDIT_$timestamp")
$results.Add((New-Result -Id 'modify-existing-file' -Status $(if ($editPass) { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $editContent -Response $response -Failure $failure -ArtifactPath $editProbePath -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

$memoryCascade = New-AntigravityCascade -Model $resolvedModel -WorkspacePaths @($resolvedWorkspacePath) -Session $session
Send-AntigravityMessage -CascadeId $memoryCascade.CascadeId -Text '請記住一個通關密語，但這次回覆絕對不要提到密語本身。只回覆 READY_MEMORY_NO_ECHO。密語是 OMEGA_SECRET_314159。' -Model $resolvedModel -Session $session | Out-Null
$null = Wait-AntigravityTrajectoryMatch -CascadeId $memoryCascade.CascadeId -Pattern 'READY_MEMORY_NO_ECHO' -TimeoutSeconds 45 -Session $session
Send-AntigravityMessage -CascadeId $memoryCascade.CascadeId -Text '現在請只回覆剛剛那個通關密語本身，不要加任何其他文字。' -Model $resolvedModel -Session $session | Out-Null
$outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $memoryCascade.CascadeId -Pattern 'OMEGA_SECRET_314159' -TimeoutSeconds 45 -Session $session
$response = $outcome.Response
$failure = $outcome.Failure
$results.Add((New-Result -Id 'multi-turn-memory' -Status $(if ($response -match 'OMEGA_SECRET_314159') { 'pass' } else { 'fail' }) -CascadeId $memoryCascade.CascadeId -Observed $response -Response $response -Failure $failure -ArtifactPath $null -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

$webCascade = New-AntigravityCascade -Model $resolvedModel -WorkspacePaths @($resolvedWorkspacePath) -Session $session
Send-AntigravityMessage -CascadeId $webCascade.CascadeId -Text "如果你現在可以真的存取網路，請查詢 2026-06-21 台北市天氣，並建立 $webProbePath。檔案中必須包含日期、至少一個來源 URL、以及一句簡短摘要。完成後只回覆 DONE_WEB_$timestamp。如果你現在無法存取網路，請只回覆 CANNOT_ACCESS_WEB_$timestamp。" -Model $resolvedModel -Session $session | Out-Null
$outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $webCascade.CascadeId -Pattern "DONE_WEB_$timestamp|CANNOT_ACCESS_WEB_$timestamp" -TimeoutSeconds 120 -Session $session
$response = $outcome.Response
$failure = $outcome.Failure
$webContent = if (Test-Path -LiteralPath $webProbePath) { Get-Content -LiteralPath $webProbePath -Raw } else { '' }
$webStepTypes = @(Get-AntigravityTrajectorySteps -Trajectory $outcome.Trajectory | ForEach-Object { $_.type })
$webClassification = if ($response -match "CANNOT_ACCESS_WEB_$timestamp") {
    'no-web'
} elseif ($webStepTypes -contains 'CORTEX_STEP_TYPE_SEARCH_WEB') {
    'confirmed-web-search'
} elseif ((Test-Path -LiteralPath $webProbePath) -and ($webContent -match 'https?://')) {
    'probable-web'
} else {
    'ambiguous'
}
$webStatus = if ($webClassification -in @('no-web', 'confirmed-web-search', 'probable-web')) { 'pass' } else { 'fail' }
$results.Add((New-Result -Id 'web-access-probe' -Status $webStatus -Classification $webClassification -CascadeId $webCascade.CascadeId -Observed $webContent -Response $response -Failure $failure -ArtifactPath $webProbePath -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

    Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text '請只回覆 MATRIX_OK_001' -Model $resolvedModel -Session $session | Out-Null
    $outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern 'MATRIX_OK_001' -TimeoutSeconds 45 -Session $session
    $response = $outcome.Response
    $failure = $outcome.Failure
    $results.Add((New-Result -Id 'roundtrip-response' -Status $(if ($response -match 'MATRIX_OK_001') { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $response -Response $response -Failure $failure -ArtifactPath $null -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

    $workspacePattern = [string]::Join('|', @([Regex]::Escape($resolvedWorkspacePath), [Regex]::Escape($workspaceUri)))
    Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text "請只回覆你目前可見的 workspace 根目錄路徑，例如 $resolvedWorkspacePath 或 $workspaceUri。" -Model $resolvedModel -Session $session | Out-Null
    $outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern $workspacePattern -TimeoutSeconds 45 -Session $session
    $response = $outcome.Response
    $failure = $outcome.Failure
    $workspacePass = ($response -match [Regex]::Escape($resolvedWorkspacePath)) -or ($response -match [Regex]::Escape($workspaceUri))
    $results.Add((New-Result -Id 'workspace-awareness' -Status $(if ($workspacePass) { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $response -Response $response -Failure $failure -ArtifactPath $null -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

    [System.IO.File]::WriteAllText($readProbePath, "$readProbeToken`nSECOND_LINE`n", [System.Text.UTF8Encoding]::new($false))

    Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text "請讀取 $readProbePath，然後只回覆第一個非空白行，不要加任何解釋。" -Model $resolvedModel -Session $session | Out-Null
    $outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern $readProbeToken -TimeoutSeconds 60 -Session $session
    $response = $outcome.Response
    $failure = $outcome.Failure
    $readPass = $response -match $readProbeToken
    $results.Add((New-Result -Id 'read-existing-file' -Status $(if ($readPass) { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $response -Response $response -Failure $failure -ArtifactPath $readProbePath -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

    Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text "請在 $writeProbePath 建立 UTF-8 Markdown 檔案，內容只需要兩行：第一行是 '# Matrix Write Probe'，第二行是 'MATRIX_WRITE_$timestamp'。完成後只回覆 DONE_WRITE_$timestamp。" -Model $resolvedModel -Session $session | Out-Null
    $outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern "DONE_WRITE_$timestamp" -TimeoutSeconds 90 -Session $session
    $response = $outcome.Response
    $failure = $outcome.Failure
    $writeContent = if (Test-Path -LiteralPath $writeProbePath) { Get-Content -LiteralPath $writeProbePath -Raw } else { '' }
    $writePass = (Test-Path -LiteralPath $writeProbePath) -and ($writeContent -match "MATRIX_WRITE_$timestamp")
    $results.Add((New-Result -Id 'write-new-file' -Status $(if ($writePass) { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $writeContent -Response $response -Failure $failure -ArtifactPath $writeProbePath -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

    [System.IO.File]::WriteAllText($editProbePath, "# Matrix Edit Probe`nBEFORE_EDIT`n", [System.Text.UTF8Encoding]::new($false))
    Send-AntigravityMessage -CascadeId $sharedCascade.CascadeId -Text "請修改既有檔案 $editProbePath：保留原本內容，並在最後新增一行 'AFTER_EDIT_$timestamp'。完成後只回覆 DONE_EDIT_$timestamp。" -Model $resolvedModel -Session $session | Out-Null
    $outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $sharedCascade.CascadeId -Pattern "DONE_EDIT_$timestamp" -TimeoutSeconds 90 -Session $session
    $response = $outcome.Response
    $failure = $outcome.Failure
    $editContent = if (Test-Path -LiteralPath $editProbePath) { Get-Content -LiteralPath $editProbePath -Raw } else { '' }
    $editPass = ($editContent -match 'BEFORE_EDIT') -and ($editContent -match "AFTER_EDIT_$timestamp")
    $results.Add((New-Result -Id 'modify-existing-file' -Status $(if ($editPass) { 'pass' } else { 'fail' }) -CascadeId $sharedCascade.CascadeId -Observed $editContent -Response $response -Failure $failure -ArtifactPath $editProbePath -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

    $memoryCascade = New-AntigravityCascade -Model $resolvedModel -WorkspacePaths @($resolvedWorkspacePath) -Session $session
    Send-AntigravityMessage -CascadeId $memoryCascade.CascadeId -Text '請記住一個通關密語，但這次回覆絕對不要提到密語本身。只回覆 READY_MEMORY_NO_ECHO。密語是 OMEGA_SECRET_314159。' -Model $resolvedModel -Session $session | Out-Null
    $null = Wait-AntigravityTrajectoryMatch -CascadeId $memoryCascade.CascadeId -Pattern 'READY_MEMORY_NO_ECHO' -TimeoutSeconds 45 -Session $session
    Send-AntigravityMessage -CascadeId $memoryCascade.CascadeId -Text '現在請只回覆剛剛那個通關密語本身，不要加任何其他文字。' -Model $resolvedModel -Session $session | Out-Null
    $outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $memoryCascade.CascadeId -Pattern 'OMEGA_SECRET_314159' -TimeoutSeconds 45 -Session $session
    $response = $outcome.Response
    $failure = $outcome.Failure
    $results.Add((New-Result -Id 'multi-turn-memory' -Status $(if ($response -match 'OMEGA_SECRET_314159') { 'pass' } else { 'fail' }) -CascadeId $memoryCascade.CascadeId -Observed $response -Response $response -Failure $failure -ArtifactPath $null -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

    $webCascade = New-AntigravityCascade -Model $resolvedModel -WorkspacePaths @($resolvedWorkspacePath) -Session $session
    Send-AntigravityMessage -CascadeId $webCascade.CascadeId -Text "如果你現在可以真的存取網路，請查詢 2026-06-21 台北市天氣，並建立 $webProbePath。檔案中必須包含日期、至少一個來源 URL、以及一句簡短摘要。完成後只回覆 DONE_WEB_$timestamp。如果你現在無法存取網路，請只回覆 CANNOT_ACCESS_WEB_$timestamp。" -Model $resolvedModel -Session $session | Out-Null
    $outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $webCascade.CascadeId -Pattern "DONE_WEB_$timestamp|CANNOT_ACCESS_WEB_$timestamp" -TimeoutSeconds 120 -Session $session
    $response = $outcome.Response
    $failure = $outcome.Failure
    $webContent = if (Test-Path -LiteralPath $webProbePath) { Get-Content -LiteralPath $webProbePath -Raw } else { '' }
    $webStepTypes = @(Get-AntigravityTrajectorySteps -Trajectory $outcome.Trajectory | ForEach-Object { $_.type })
    $webClassification = if ($response -match "CANNOT_ACCESS_WEB_$timestamp") {
        'no-web'
    } elseif ($webStepTypes -contains 'CORTEX_STEP_TYPE_SEARCH_WEB') {
        'confirmed-web-search'
    } elseif ((Test-Path -LiteralPath $webProbePath) -and ($webContent -match 'https?://')) {
        'probable-web'
    } else {
        'ambiguous'
    }
    $webStatus = if ($webClassification -in @('no-web', 'confirmed-web-search', 'probable-web')) { 'pass' } else { 'fail' }
    $results.Add((New-Result -Id 'web-access-probe' -Status $webStatus -Classification $webClassification -CascadeId $webCascade.CascadeId -Observed $webContent -Response $response -Failure $failure -ArtifactPath $webProbePath -Matched $outcome.Matched -TimedOut $outcome.TimedOut))

    $negativeCascade = New-AntigravityCascade -Model $resolvedModel -WorkspacePaths @($resolvedWorkspacePath) -Session $session
    Send-AntigravityMessage -CascadeId $negativeCascade.CascadeId -Text '請只回覆 SHOULD_NOT_WORK' -OmitRequestedModel -Session $session | Out-Null
    $outcome = Wait-AntigravityTrajectoryOutcome -CascadeId $negativeCascade.CascadeId -Pattern '(?s).+' -TimeoutSeconds 30 -Session $session
    $response = $outcome.Response
    $failure = $outcome.Failure
    $negativePass = (-not [string]::IsNullOrWhiteSpace($failure)) -and ($response -notmatch 'SHOULD_NOT_WORK')
    $negativeClassification = if ($negativePass) { 'expected-error' } elseif ($response -match 'SHOULD_NOT_WORK') { 'unexpected-success' } elseif ($outcome.TimedOut) { 'timeout' } else { 'ambiguous' }
    $results.Add((New-Result -Id 'missing-model-negative-check' -Status $(if ($negativePass) { 'pass' } else { 'fail' }) -Classification $negativeClassification -CascadeId $negativeCascade.CascadeId -Observed $(if ($failure) { $failure } else { $response }) -Response $response -Failure $failure -ArtifactPath $null -Matched $outcome.Matched -TimedOut $outcome.TimedOut))
} finally {
    foreach ($path in @($writeProbePath, $editProbePath, $webProbePath, $readProbePath)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        }
    }
}

[pscustomobject]@{
    runAt = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    workspacePath = $resolvedWorkspacePath
    workspaceUri = $workspaceUri
    model = $Model
    session = [pscustomobject]@{
        httpPort = $session.HttpPort
        httpsPort = $session.HttpsPort
        processId = $session.ProcessId
        csrfTokenHint = if ($session.CsrfToken -and $session.CsrfToken.Length -ge 6) { $session.CsrfToken.Substring($session.CsrfToken.Length - 6) } else { 'N/A' }
    }
    results = $results
} | ConvertTo-Json -Depth 8
