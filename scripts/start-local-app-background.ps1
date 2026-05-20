Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot "run-local-app.ps1"
$stdout = Join-Path $workspace "server-live.stdout.log"
$stderr = Join-Path $workspace "server-live.stderr.log"
$pwsh = "C:\Users\samsonlee\AppData\Local\Microsoft\WindowsApps\pwsh.exe"
$port = 8000

$deadline = (Get-Date).AddSeconds(15)
while ($true) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) {
        break
    }
    if ((Get-Date) -ge $deadline) {
        throw "Port $port is still in use by process $($listener.OwningProcess)."
    }
    Start-Sleep -Milliseconds 500
}

$process = Start-Process `
    -FilePath $pwsh `
    -ArgumentList "-ExecutionPolicy", "Bypass", "-File", $launcher `
    -WorkingDirectory $workspace `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

$process.Id
