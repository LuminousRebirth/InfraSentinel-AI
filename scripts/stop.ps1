[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $projectRoot "runtime/api.pid"

function Stop-InfraProcess {
    param([string]$PidFile, [string]$CommandPattern)
    $processId = [int](Get-Content -Raw -LiteralPath $PidFile)
    $running = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" `
        -ErrorAction SilentlyContinue
    if ($null -ne $running -and $running.CommandLine -match $CommandPattern) {
        Stop-Process -Id $processId -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile -Force
}

foreach ($workerPidPath in Get-ChildItem -LiteralPath (Join-Path $projectRoot "runtime") `
    -Filter "worker-*.pid" -File -ErrorAction SilentlyContinue) {
    Stop-InfraProcess $workerPidPath.FullName "infrasentinel\.worker"
}

if (Test-Path -LiteralPath $pidPath) {
    Stop-InfraProcess $pidPath "uvicorn.*infrasentinel\.main:app"
}

Push-Location $projectRoot
try {
    docker compose --env-file .env stop
} finally {
    Pop-Location
}
Write-Host "InfraSentinel services stopped; persistent data was retained."
