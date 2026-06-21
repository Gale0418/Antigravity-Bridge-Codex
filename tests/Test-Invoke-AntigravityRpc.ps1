$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\..\scripts\Invoke-AntigravityRpc.ps1"

$trajectoryUri = Get-AntigravityServiceUri -HttpPort 50609 -Method 'GetCascadeTrajectory'
if ($trajectoryUri -ne 'http://127.0.0.1:50609/exa.language_server_pb.LanguageServerService/GetCascadeTrajectory') {
    throw "Unexpected trajectory uri: $trajectoryUri"
}

$workspaceUri = ConvertTo-AntigravityFileUri -Path 'D:\MyGame'
if ($workspaceUri -ne 'file:///d:/MyGame') {
    throw "Unexpected workspace uri: $workspaceUri"
}

Write-Host 'PASS: rpc helper values look correct'
