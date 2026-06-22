$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\..\scripts\Invoke-AntigravityRpc.ps1"

$trajectoryUri = Get-AntigravityServiceUri -HttpPort 50609 -Method 'GetCascadeTrajectory'
if ($trajectoryUri -ne 'http://127.0.0.1:50609/exa.language_server_pb.LanguageServerService/GetCascadeTrajectory') {
    throw "Unexpected trajectory uri: $trajectoryUri"
}

$tempPath = [System.IO.Path]::GetFullPath($env:TEMP)
$workspaceUri = ConvertTo-AntigravityFileUri -Path $tempPath
$driveLetter = $tempPath.Substring(0, 1).ToLowerInvariant()
$remainder = $tempPath.Substring(2).Replace('\', '/')
$expectedUri = "file:///${driveLetter}:$remainder"
if ($workspaceUri -ne $expectedUri) {
    throw "Unexpected workspace uri: $workspaceUri expected: $expectedUri"
}

Write-Host 'PASS: rpc helper values look correct'
