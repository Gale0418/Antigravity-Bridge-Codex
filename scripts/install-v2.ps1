$ErrorActionPreference = 'Stop'

$python = $null
foreach ($candidate in @('python3', 'python', 'py')) {
    $command = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        $python = $command.Source
        break
    }
}
if (-not $python) {
    throw 'Python is required for the compatibility installer but was not found on PATH.'
}

$installer = Join-Path $PSScriptRoot 'install_v2.py'
& $python $installer
if ($LASTEXITCODE -ne 0) {
    throw "Antigravity Bridge Codex v2 installer failed with exit code $LASTEXITCODE"
}
