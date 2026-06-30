$ErrorActionPreference = 'Stop'

function Copy-FreshItem {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    if (-not (Test-Path -LiteralPath $SourcePath)) {
        return
    }

    if (Test-Path -LiteralPath $DestinationPath) {
        Remove-Item -LiteralPath $DestinationPath -Recurse -Force
    }

    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Recurse -Force
}

function Ensure-ParentDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
}

function Get-CodexHome {
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        return $env:CODEX_HOME
    }

    if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        return (Join-Path $env:USERPROFILE '.codex')
    }

    if (-not [string]::IsNullOrWhiteSpace($HOME)) {
        return (Join-Path $HOME '.codex')
    }

    throw 'Cannot resolve CODEX_HOME. Set CODEX_HOME, USERPROFILE, or HOME before running the installer.'
}

function Get-CodexExecutable {
    $codexHome = Get-CodexHome
    $sandboxCandidates = @(
        (Join-Path $codexHome '.sandbox-bin/codex'),
        (Join-Path $codexHome '.sandbox-bin/codex.exe')
    )

    foreach ($candidate in $sandboxCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    foreach ($commandName in @('codex', 'codex.exe')) {
        $codexCommand = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($codexCommand) {
            return $codexCommand.Source
        }
    }

    return $null
}

function Invoke-NativeOrThrow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

$sourceRoot = $PSScriptRoot
$codexHome = Get-CodexHome
$skillRoot = Join-Path $codexHome 'skills/antigravity-gemini-bridge'
$marketplaceRoot = Join-Path $codexHome 'local-marketplaces/antigravity-gemini-bridge'
$marketplaceManifestPath = Join-Path $marketplaceRoot '.agents/plugins/marketplace.json'
$pluginRoot = Join-Path $marketplaceRoot 'plugins/antigravity-gemini-bridge'
$pluginSkillRoot = Join-Path $pluginRoot 'skills/antigravity-gemini-bridge'
$repoPluginManifestPath = Join-Path $sourceRoot '.codex-plugin/plugin.json'
$installedPluginManifestPath = Join-Path $pluginRoot '.codex-plugin/plugin.json'

$skillItems = @(
    'SKILL.md',
    'agents',
    'assets',
    'references',
    'scripts',
    'mcp',
    '.mcp.json'
)

if (-not (Test-Path -LiteralPath $skillRoot)) {
    New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
}

Write-Host "Installing personal skill from $sourceRoot to $skillRoot"
foreach ($item in $skillItems) {
    Copy-FreshItem -SourcePath (Join-Path $sourceRoot $item) -DestinationPath (Join-Path $skillRoot $item)
}

if (-not (Test-Path -LiteralPath $repoPluginManifestPath)) {
    Write-Warning "Skipping local plugin sync because $repoPluginManifestPath is missing."
    Write-Host 'Install completed.'
    return
}

Write-Host "Syncing local plugin package to $pluginRoot"
New-Item -ItemType Directory -Path $pluginSkillRoot -Force | Out-Null

Copy-FreshItem -SourcePath (Join-Path $sourceRoot '.codex-plugin') -DestinationPath (Join-Path $pluginRoot '.codex-plugin')
Copy-FreshItem -SourcePath (Join-Path $sourceRoot '.mcp.json') -DestinationPath (Join-Path $pluginRoot '.mcp.json')
Copy-FreshItem -SourcePath (Join-Path $sourceRoot 'assets') -DestinationPath (Join-Path $pluginRoot 'assets')
Copy-FreshItem -SourcePath (Join-Path $sourceRoot 'mcp') -DestinationPath (Join-Path $pluginRoot 'mcp')
Copy-FreshItem -SourcePath (Join-Path $sourceRoot 'scripts') -DestinationPath (Join-Path $pluginRoot 'scripts')

foreach ($item in $skillItems) {
    Copy-FreshItem -SourcePath (Join-Path $sourceRoot $item) -DestinationPath (Join-Path $pluginSkillRoot $item)
}

$pluginManifest = Get-Content -LiteralPath $installedPluginManifestPath -Raw | ConvertFrom-Json
$pluginManifest.version = '0.1.0+codex.' + (Get-Date -Format 'yyyyMMddHHmmss')
Ensure-ParentDirectory -Path $installedPluginManifestPath
$pluginManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $installedPluginManifestPath -Encoding utf8

$marketplaceManifest = @{
    name = 'antigravity-gemini-bridge-local'
    interface = @{ displayName = 'Local Antigravity Bridge Codex' }
    plugins = @(
        @{
            name = 'antigravity-gemini-bridge'
            source = @{
                source = 'local'
                path = './plugins/antigravity-gemini-bridge'
            }
            policy = @{
                installation = 'AVAILABLE'
                authentication = 'ON_INSTALL'
            }
            category = 'Productivity'
        }
    )
}
Ensure-ParentDirectory -Path $marketplaceManifestPath
$marketplaceManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $marketplaceManifestPath -Encoding utf8

$codexExe = Get-CodexExecutable
if (-not $codexExe) {
    Write-Warning 'Codex executable not found; local plugin files were synced but not registered.'
    Write-Host 'Install completed.'
    return
}

Write-Host "Registering marketplace with $codexExe"
Invoke-NativeOrThrow -FilePath $codexExe -Arguments @('plugin', 'marketplace', 'add', $marketplaceRoot)
Write-Host 'Installing or refreshing local plugin antigravity-gemini-bridge@antigravity-gemini-bridge-local'
Invoke-NativeOrThrow -FilePath $codexExe -Arguments @('plugin', 'add', 'antigravity-gemini-bridge@antigravity-gemini-bridge-local')

Write-Host 'Install completed.'
