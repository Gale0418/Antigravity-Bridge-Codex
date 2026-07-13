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

function Invoke-NativeBestEffort {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    try {
        & $FilePath @Arguments *> $null
    } catch {
        return
    }
}

function Get-LegacyPluginName {
    return (('antigravity-', 'gemini', '-bridge') -join '')
}

function Test-IsWindowsPlatform {
    if ($PSVersionTable.PSEdition -eq 'Desktop') {
        return $true
    }

    return [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )
}

function Test-IsWindowsStorePythonAlias {
    param([string]$Path)

    return (Test-IsWindowsPlatform) -and ($Path -like '*\Microsoft\WindowsApps\python*.exe')
}

function Resolve-McpPythonCommand {
    foreach ($commandName in @('python3', 'python')) {
        $pythonCommands = Get-Command $commandName -All -CommandType Application -ErrorAction SilentlyContinue
        foreach ($pythonCommand in $pythonCommands) {
            if ($pythonCommand -and -not [string]::IsNullOrWhiteSpace($pythonCommand.Source) -and -not (Test-IsWindowsStorePythonAlias $pythonCommand.Source)) {
                return $pythonCommand.Source
            }
        }
    }

    if (Test-IsWindowsPlatform) {
        return 'python'
    }

    return 'python3'
}

function Remove-PathBestEffort {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Remove-LegacyInstall {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CodexHome,

        [string]$CodexExe
    )

    $legacyName = Get-LegacyPluginName
    $legacyMarketplace = "${legacyName}-local"

    if (-not [string]::IsNullOrWhiteSpace($CodexExe)) {
        Invoke-NativeBestEffort -FilePath $CodexExe -Arguments @('plugin', 'remove', "${legacyName}@${legacyMarketplace}")
        Invoke-NativeBestEffort -FilePath $CodexExe -Arguments @('plugin', 'marketplace', 'remove', $legacyMarketplace)
    }

    Remove-PathBestEffort -Path (Join-Path $CodexHome "skills/$legacyName")
    Remove-PathBestEffort -Path (Join-Path $CodexHome "local-marketplaces/$legacyName")
    Remove-PathBestEffort -Path (Join-Path $CodexHome "plugins/cache/$legacyMarketplace")
}

$stableMcpServerName = 'antigravity_bridge_codex'

function Register-StableMcpServer {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CodexExe,

        [Parameter(Mandatory = $true)]
        [string]$PluginRoot
    )

    $serverPath = Join-Path $PluginRoot 'mcp/antigravity_bridge_server.py'
    if (-not (Test-Path -LiteralPath $serverPath)) {
        Write-Warning "Skipping stable MCP registration because $serverPath is missing."
        return
    }

    $pythonCommand = Resolve-McpPythonCommand
    Write-Host "Registering stable MCP server $stableMcpServerName with $CodexExe"
    Invoke-NativeBestEffort -FilePath $CodexExe -Arguments @('mcp', 'remove', $stableMcpServerName)
    Invoke-NativeOrThrow -FilePath $CodexExe -Arguments @('mcp', 'add', $stableMcpServerName, '--', $pythonCommand, $serverPath)
}

function Set-InstalledMcpInterpreter {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ManifestPath
    )

    if (-not (Test-Path -LiteralPath $ManifestPath)) {
        return
    }

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $server = $manifest.mcpServers.'antigravity-bridge-codex'
    if (-not $server) {
        return
    }

    if (-not $server.type) {
        $server | Add-Member -NotePropertyName type -NotePropertyValue 'stdio'
    }

    if ($server.command -in @('python3', 'python')) {
        $server.command = Resolve-McpPythonCommand
    }

    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $ManifestPath -Encoding utf8
}

$sourceRoot = $PSScriptRoot
$codexHome = Get-CodexHome
$codexExe = Get-CodexExecutable
Remove-LegacyInstall -CodexHome $codexHome -CodexExe $codexExe

$skillRoot = Join-Path $codexHome 'skills/antigravity-bridge-codex'
$marketplaceRoot = Join-Path $codexHome 'local-marketplaces/antigravity-bridge-codex'
$marketplaceManifestPath = Join-Path $marketplaceRoot '.agents/plugins/marketplace.json'
$pluginRoot = Join-Path $marketplaceRoot 'plugins/antigravity-bridge-codex'
$pluginItems = @(
    '.codex-plugin',
    'SKILL.md',
    'agents',
    'assets',
    'references',
    'scripts',
    'skills',
    'mcp',
    '.mcp.json'
)
$repoPluginManifestPath = Join-Path $sourceRoot '.codex-plugin/plugin.json'
$installedPluginManifestPath = Join-Path $pluginRoot '.codex-plugin/plugin.json'

$requiredSkillItems = @('SKILL.md', 'scripts', 'mcp')
$optionalSkillItems = @('agents', 'assets', 'references', '.mcp.json')

function Sync-ItemsTransactional {
    param([Parameter(Mandatory = $true)][string]$SourceRoot, [Parameter(Mandatory = $true)][string]$DestinationRoot, [Parameter(Mandatory = $true)][string[]]$Items)
    $parent = Split-Path -Parent $DestinationRoot
    Ensure-ParentDirectory -Path (Join-Path $DestinationRoot 'placeholder')
    $stage = Join-Path $parent ('.' + (Split-Path -Leaf $DestinationRoot) + '.stage-' + [guid]::NewGuid().ToString('N'))
    $backup = Join-Path $parent ('.' + (Split-Path -Leaf $DestinationRoot) + '.backup-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    try {
        foreach ($item in $Items) {
            $source = Join-Path $SourceRoot $item
            if (Test-Path -LiteralPath $source) { Copy-FreshItem -SourcePath $source -DestinationPath (Join-Path $stage $item) }
        }
        if (Test-Path -LiteralPath $DestinationRoot) { Move-Item -LiteralPath $DestinationRoot -Destination $backup -Force }
        Move-Item -LiteralPath $stage -Destination $DestinationRoot -Force
        $stage = $null
    } catch {
        if (Test-Path -LiteralPath $backup) {
            if (Test-Path -LiteralPath $DestinationRoot) { Remove-Item -LiteralPath $DestinationRoot -Recurse -Force }
            Move-Item -LiteralPath $backup -Destination $DestinationRoot -Force
        }
        throw
    } finally {
        if ($stage -and (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -Recurse -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
    }
}

function Assert-RequiredItems {
    param([Parameter(Mandatory = $true)][string]$Root, [Parameter(Mandatory = $true)][string[]]$Items, [Parameter(Mandatory = $true)][string]$Label)
    $missing = @($Items | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Root $_)) })
    if ($missing.Count -gt 0) { throw "Missing required $Label item(s): $($missing -join ', ')" }
}

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

Assert-RequiredItems -Root $sourceRoot -Items $requiredSkillItems -Label 'skill'
Write-Host "Installing personal skill from $sourceRoot to $skillRoot"
Sync-ItemsTransactional -SourceRoot $sourceRoot -DestinationRoot $skillRoot -Items $skillItems
Set-InstalledMcpInterpreter -ManifestPath (Join-Path $skillRoot '.mcp.json')

if (-not (Test-Path -LiteralPath $repoPluginManifestPath)) {
    Write-Warning "Skipping local plugin sync because $repoPluginManifestPath is missing."
    Write-Host 'Install completed.'
    return
}

Assert-RequiredItems -Root $sourceRoot -Items @('.codex-plugin', 'SKILL.md', 'scripts', 'mcp') -Label 'plugin'
Write-Host "Syncing local plugin package to $pluginRoot"
New-Item -ItemType Directory -Path $pluginRoot -Force | Out-Null

Sync-ItemsTransactional -SourceRoot $sourceRoot -DestinationRoot $pluginRoot -Items $pluginItems
Set-InstalledMcpInterpreter -ManifestPath (Join-Path $pluginRoot '.mcp.json')

$pluginManifest = Get-Content -LiteralPath $installedPluginManifestPath -Raw | ConvertFrom-Json
$pluginManifest.version = '0.1.0+codex.' + (Get-Date -Format 'yyyyMMddHHmmss')
Ensure-ParentDirectory -Path $installedPluginManifestPath
$pluginManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $installedPluginManifestPath -Encoding utf8

$marketplaceManifest = @{
    name = 'antigravity-bridge-codex-local'
    interface = @{ displayName = 'Local Antigravity Bridge Codex' }
    plugins = @(
        @{
            name = 'antigravity-bridge-codex'
            source = @{
                source = 'local'
                path = './plugins/antigravity-bridge-codex'
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

if (-not $codexExe) {
    Write-Warning 'Codex executable not found; local plugin files were synced but not registered.'
    Write-Host 'Install completed.'
    return
}

Write-Host "Registering marketplace with $codexExe"
Invoke-NativeOrThrow -FilePath $codexExe -Arguments @('plugin', 'marketplace', 'add', $marketplaceRoot)
Write-Host 'Installing or refreshing local plugin antigravity-bridge-codex@antigravity-bridge-codex-local'
Invoke-NativeOrThrow -FilePath $codexExe -Arguments @('plugin', 'add', 'antigravity-bridge-codex@antigravity-bridge-codex-local')
Register-StableMcpServer -CodexExe $codexExe -PluginRoot $pluginRoot

Write-Host 'Install completed.'
