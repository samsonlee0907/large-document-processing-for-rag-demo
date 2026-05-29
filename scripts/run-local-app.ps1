param(
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $workspace ".env"
$pythonExe = "C:\Users\samsonlee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (-not (Test-Path $envFile)) {
    throw ".env not found at $envFile"
}

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
        return
    }
    $pair = $line -split "=", 2
    if ($pair.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($pair[0], $pair[1], "Process")
    }
}

Set-Location $workspace
& $pythonExe -m uvicorn backend.app:app --host 127.0.0.1 --port $Port
