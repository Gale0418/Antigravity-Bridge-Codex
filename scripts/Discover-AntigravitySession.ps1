$ErrorActionPreference = 'Stop'

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

function Get-AntigravitySessionInfo {
    param(
        [string]$MainLogPath = (Join-Path $env:APPDATA 'Antigravity\logs\main.log'),
        [string]$LanguageServerLogPath = (Join-Path $env:APPDATA 'Antigravity\logs\language_server.log')
    )

    if (-not (Test-Path -LiteralPath $MainLogPath)) {
        throw "Antigravity main log not found: $MainLogPath"
    }

    if (-not (Test-Path -LiteralPath $LanguageServerLogPath)) {
        throw "Antigravity language server log not found: $LanguageServerLogPath"
    }

    $mainLogText = Get-Content -LiteralPath $MainLogPath -Raw
    $languageServerLogText = Get-Content -LiteralPath $LanguageServerLogPath -Raw

    $session = Get-AntigravitySessionInfoFromText `
        -MainLogText $mainLogText `
        -LanguageServerLogText $languageServerLogText

    $session | Add-Member -NotePropertyName MainLogPath -NotePropertyValue $MainLogPath
    $session | Add-Member -NotePropertyName LanguageServerLogPath -NotePropertyValue $LanguageServerLogPath
    return $session
}