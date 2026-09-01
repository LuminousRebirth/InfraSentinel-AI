[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $projectRoot "runtime/api.pid"

if (Test-Path -LiteralPath $pidPath) {
    $apiPid = [int](Get-Content -Raw -LiteralPath $pidPath)
    Stop-Process -Id $apiPid -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidPath -Force
}

Push-Location $projectRoot
try {
    docker compose --env-file .env stop
} finally {
    Pop-Location
}
Write-Host "InfraSentinel services stopped; persistent data was retained."
