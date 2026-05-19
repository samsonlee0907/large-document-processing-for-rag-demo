Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot "run-local-app.ps1"
$stdout = Join-Path $workspace "server-live.stdout.log"
$stderr = Join-Path $workspace "server-live.stderr.log"
$pwsh = "C:\Users\samsonlee\AppData\Local\Microsoft\WindowsApps\pwsh.exe"

$process = Start-Process `
    -FilePath $pwsh `
    -ArgumentList "-ExecutionPolicy", "Bypass", "-File", $launcher `
    -WorkingDirectory $workspace `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

$process.Id
