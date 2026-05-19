Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Start-Sleep -Seconds 6

try {
    (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health).Content
}
catch {
    $_.Exception.Message
}
