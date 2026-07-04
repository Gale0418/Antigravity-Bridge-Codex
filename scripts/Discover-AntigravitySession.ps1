$ErrorActionPreference = 'Stop'

function Get-AntigravityPlatform {
    param([string]$Platform = '')

    if (-not [string]::IsNullOrWhiteSpace($Platform)) {
        return $Platform
    }

    if (Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) {
        if ($IsWindows) { return 'Windows' }
        if ($IsMacOS) { return 'macOS' }
        if ($IsLinux) { return 'Linux' }
    }

    $description = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    if ($description -match 'Darwin|macOS|Mac') {
        return 'macOS'
    }
    if ($description -match 'Linux') {
        return 'Linux'
    }
    return 'Windows'
}

function Get-LastRegexValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$Pattern,

        [int]$Group = 1
    )

    $matches = [System.Text.RegularExpressions.Regex]::Matches(
        $Text,
        $Pattern,
        [System.Text.RegularExpressions.RegexOptions]::Multiline
    )

    if ($matches.Count -eq 0) {
        return $null
    }

    return $matches[$matches.Count - 1].Groups[$Group].Value
}

function Get-AntigravitySessionInfoFromText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MainLogText,

        [Parameter(Mandatory = $true)]
        [string]$LanguageServerLogText
    )

    $csrfToken = Get-LastRegexValue -Text $MainLogText -Pattern '--csrf_token\s+([0-9a-fA-F-]{36})'
    $localUrl = Get-LastRegexValue -Text $MainLogText -Pattern 'Local:\s+(https://127\.0\.0\.1:(\d+)/)' -Group 1
    if (-not $localUrl) {
        $localUrl = Get-LastRegexValue -Text $MainLogText -Pattern 'URL:\s+(https://127\.0\.0\.1:(\d+)/)' -Group 1
    }

    $localHttpsPort = Get-LastRegexValue -Text $MainLogText -Pattern 'Local:\s+https://127\.0\.0\.1:(\d+)/' -Group 1
    if (-not $localHttpsPort) {
        $localHttpsPort = Get-LastRegexValue -Text $MainLogText -Pattern 'URL:\s+https://127\.0\.0\.1:(\d+)/' -Group 1
    }

    $processId = Get-LastRegexValue -Text $LanguageServerLogText -Pattern 'process with pid\s+(\d+)' -Group 1
    $httpsPort = Get-LastRegexValue -Text $LanguageServerLogText -Pattern 'port at\s+(\d+)\s+for HTTPS' -Group 1
    $httpPort = Get-LastRegexValue -Text $LanguageServerLogText -Pattern 'port at\s+(\d+)\s+for HTTP' -Group 1

    if (-not $csrfToken) {
        throw 'Unable to locate Antigravity CSRF token in main.log'
    }

    if (-not $localUrl) {
        throw 'Unable to locate Antigravity local URL in main.log'
    }

    if (-not $httpsPort) {
        $httpsPort = $localHttpsPort
    }

    if (-not $httpsPort -or -not $httpPort) {
        throw 'Unable to locate Antigravity HTTP/HTTPS ports in language_server.log'
    }

    if (-not $processId) {
        throw 'Unable to locate Antigravity language server pid in language_server.log'
    }

    [pscustomobject]@{
        CsrfToken = $csrfToken
        LocalUrl = $localUrl
        HttpsPort = [int]$httpsPort
        HttpPort = [int]$httpPort
        ProcessId = [int]$processId
    }
}

function Get-AntigravityDefaultLogPathCandidates {
    param(
        [string]$Platform = '',
        [string]$HomeDirectory = $HOME,
        [string]$AppDataDirectory = $env:APPDATA
    )

    $resolvedPlatform = Get-AntigravityPlatform -Platform $Platform
    $mainCandidates = New-Object System.Collections.Generic.List[string]
    $languageCandidates = New-Object System.Collections.Generic.List[string]

    switch ($resolvedPlatform) {
        'Windows' {
            $baseDirectory = if (-not [string]::IsNullOrWhiteSpace($AppDataDirectory)) {
                Join-Path $AppDataDirectory 'Antigravity\logs'
            } elseif (-not [string]::IsNullOrWhiteSpace($HomeDirectory)) {
                Join-Path $HomeDirectory 'AppData\Roaming\Antigravity\logs'
            } else {
                ''
            }

            if (-not [string]::IsNullOrWhiteSpace($baseDirectory)) {
                $mainCandidates.Add((Join-Path $baseDirectory 'main.log'))
                $languageCandidates.Add((Join-Path $baseDirectory 'language_server.log'))
            }
        }
        'macOS' {
            $mainCandidates.Add((Join-Path $HomeDirectory 'Library/Logs/Antigravity/main.log'))
            $languageCandidates.Add((Join-Path $HomeDirectory 'Library/Logs/Antigravity/language_server.log'))

            $snapshotRoot = Join-Path $HomeDirectory 'Library/Application Support/Antigravity/logs'
            if (Test-Path -LiteralPath $snapshotRoot) {
                $snapshotDirectories = Get-ChildItem -LiteralPath $snapshotRoot -Directory -ErrorAction SilentlyContinue |
                    Sort-Object Name -Descending

                foreach ($directory in $snapshotDirectories) {
                    $mainCandidates.Add((Join-Path $directory.FullName 'main.log'))
                    $languageCandidates.Add((Join-Path $directory.FullName 'ls-main.log'))

                    $rotatedLogs = Get-ChildItem -LiteralPath $directory.FullName -File -Filter 'ls-main.*.log' -ErrorAction SilentlyContinue |
                        Sort-Object Name -Descending
                    foreach ($log in $rotatedLogs) {
                        $languageCandidates.Add($log.FullName)
                    }
                }
            }
        }
        'Linux' {
            $mainCandidates.Add((Join-Path $HomeDirectory '.config/Antigravity/logs/main.log'))
            $languageCandidates.Add((Join-Path $HomeDirectory '.config/Antigravity/logs/language_server.log'))
            $mainCandidates.Add((Join-Path $HomeDirectory '.local/share/Antigravity/logs/main.log'))
            $languageCandidates.Add((Join-Path $HomeDirectory '.local/share/Antigravity/logs/language_server.log'))
        }
    }

    [pscustomobject]@{
        Platform = $resolvedPlatform
        MainLogCandidates = @($mainCandidates | Select-Object -Unique)
        LanguageServerLogCandidates = @($languageCandidates | Select-Object -Unique)
    }
}

function Resolve-AntigravityLogPath {
    param(
        [string]$ProvidedPath,
        [string[]]$Candidates,
        [string]$Label
    )

    if (-not [string]::IsNullOrWhiteSpace($ProvidedPath)) {
        if (-not (Test-Path -LiteralPath $ProvidedPath)) {
            throw "Antigravity $Label not found: $ProvidedPath"
        }
        return $ProvidedPath
    }

    foreach ($candidate in $Candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    $checked = if ($Candidates) { $Candidates -join ', ' } else { '<none>' }
    throw "Antigravity $Label not found. Checked: $checked"
}

function ConvertTo-AntigravitySessionPublicInfo {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Session,

        [switch]$ShowSecret
    )

    [pscustomobject]@{
        LocalUrl = $Session.LocalUrl
        HttpsPort = $Session.HttpsPort
        HttpPort = $Session.HttpPort
        ProcessId = $Session.ProcessId
        CsrfToken = $(if ($ShowSecret) { $Session.CsrfToken } else { '<redacted>' })
    }
}

function Get-AntigravitySessionInfo {
    param(
        [string]$MainLogPath = '',
        [string]$LanguageServerLogPath = '',
        [string]$Platform = '',
        [string]$HomeDirectory = $HOME,
        [string]$AppDataDirectory = $env:APPDATA
    )

    $candidates = Get-AntigravityDefaultLogPathCandidates `
        -Platform $Platform `
        -HomeDirectory $HomeDirectory `
        -AppDataDirectory $AppDataDirectory

    $resolvedMainLogPath = Resolve-AntigravityLogPath `
        -ProvidedPath $MainLogPath `
        -Candidates $candidates.MainLogCandidates `
        -Label 'main log'

    $resolvedLanguageServerLogPath = Resolve-AntigravityLogPath `
        -ProvidedPath $LanguageServerLogPath `
        -Candidates $candidates.LanguageServerLogCandidates `
        -Label 'language server log'

    $mainLogText = Get-Content -LiteralPath $resolvedMainLogPath -Raw
    $languageServerLogText = Get-Content -LiteralPath $resolvedLanguageServerLogPath -Raw

    $session = Get-AntigravitySessionInfoFromText `
        -MainLogText $mainLogText `
        -LanguageServerLogText $languageServerLogText

    $session | Add-Member -NotePropertyName MainLogPath -NotePropertyValue $resolvedMainLogPath
    $session | Add-Member -NotePropertyName LanguageServerLogPath -NotePropertyValue $resolvedLanguageServerLogPath
    return $session
}
