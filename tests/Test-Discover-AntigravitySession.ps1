$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\..\scripts\Discover-AntigravitySession.ps1"

$mainLog = @'
[2026-06-21 14:08:00.705] [info]
Spawning: C:\Users\USER\AppData\Local\Programs\Antigravity\resources\bin\language_server.exe --standalone --csrf_token 67e9756a-599c-4c46-a6df-ea7e714b7d8f --app_data_dir antigravity
[2026-06-21 14:08:00.932] [info]  [Auto-Restart] Port changed! Reloading all windows with URL: https://127.0.0.1:50608/
'@

$languageLog = @'
I0621 14:08:00.827049 30980 server.go:1296] Starting language server process with pid 30980
I0621 14:08:00.932924 30980 server.go:493] Language server listening on random port at 50608 for HTTPS (gRPC)
I0621 14:08:00.933429 30980 server.go:500] Language server listening on random port at 50609 for HTTP
'@

$session = Get-AntigravitySessionInfoFromText -MainLogText $mainLog -LanguageServerLogText $languageLog

if ($session.CsrfToken -ne '67e9756a-599c-4c46-a6df-ea7e714b7d8f') {
    throw "Expected csrf token to parse, got '$($session.CsrfToken)'"
}

if ($session.HttpsPort -ne 50608) {
    throw "Expected https port 50608, got '$($session.HttpsPort)'"
}

if ($session.HttpPort -ne 50609) {
    throw "Expected http port 50609, got '$($session.HttpPort)'"
}

if ($session.ProcessId -ne 30980) {
    throw "Expected pid 30980, got '$($session.ProcessId)'"
}

if ($session.LocalUrl -ne 'https://127.0.0.1:50608/') {
    throw "Expected local url to parse, got '$($session.LocalUrl)'"
}


$publicSession = ConvertTo-AntigravitySessionPublicInfo -Session $session
if ($publicSession.CsrfToken -ne '<redacted>') {
    throw "Expected csrf token to be redacted, got '$($publicSession.CsrfToken)'"
}

$secretSession = ConvertTo-AntigravitySessionPublicInfo -Session $session -ShowSecret
if ($secretSession.CsrfToken -ne $session.CsrfToken) {
    throw 'Expected ShowSecret to preserve csrf token'
}

Write-Host 'PASS: discovery parser fixtures look correct'
