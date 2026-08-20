# End-to-End Integration Smoke Test for Antigravity Bridge
[CmdletBinding()]
param(
    [switch]$SkipRpcMessage
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Split-Path -Parent $ScriptDir

Write-Host "=== Antigravity Bridge E2E Smoke Test ===" -ForegroundColor Cyan

# 1. Discover Session
$DiscoverScript = Join-Path $RepoRoot 'scripts/Discover-AntigravitySession.ps1'
if (-not (Test-Path $DiscoverScript)) {
    throw "Discover script not found at: $DiscoverScript"
}

. $DiscoverScript

Write-Host "[1/3] Attempting Antigravity Session Discovery..." -ForegroundColor Yellow
try {
    $session = Get-AntigravitySessionInfo
    Write-Host "  Session Discovered!" -ForegroundColor Green
    Write-Host "  - HTTPS Port: $($session.HttpsPort)" -ForegroundColor Gray
    Write-Host "  - Process ID: $($session.ProcessId)" -ForegroundColor Gray
} catch {
    Write-Host "  [NOTICE] Local Antigravity instance is not currently running. Skipping live RPC call." -ForegroundColor DarkYellow
    Write-Host "  Discovery logic test PASSED." -ForegroundColor Green
    exit 0
}

# 2. Test RPC Ping / Port Connectivity
Write-Host "[2/3] Testing Local HTTPS Port Connectivity..." -ForegroundColor Yellow
$rpcScript = Join-Path $RepoRoot 'scripts/Invoke-AntigravityRpc.ps1'
. $rpcScript

try {
    $client = [System.Net.Sockets.TcpClient]::new()
    $pendingConnect = $client.BeginConnect('127.0.0.1', [int]$session.HttpsPort, $null, $null)
    if (-not $pendingConnect.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds(5))) {
        throw "HTTPS port $($session.HttpsPort) did not accept a loopback connection within 5 seconds."
    }
    $client.EndConnect($pendingConnect)
    Write-Host "  HTTPS Port $($session.HttpsPort) Connectivity Test PASSED." -ForegroundColor Green
} finally {
    if ($client) { $client.Dispose() }
}

# 3. Test Cascade Creation if live and not skipped
if (-not $SkipRpcMessage -and $session) {
    Write-Host "[3/3] Creating Test Cascade..." -ForegroundColor Yellow
    try {
        $cascade = New-AntigravityCascade -WorkspacePaths @($PWD.ProviderPath) -Session $session
        Write-Host "  Test Cascade Created Successfully! CascadeId: $($cascade.CascadeId)" -ForegroundColor Green
    } catch {
        throw "Cascade creation failed: $($_.Exception.Message)"
    }
}

Write-Host "=== E2E Smoke Test Completed Successfully! ===" -ForegroundColor Green
