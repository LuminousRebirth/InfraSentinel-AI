[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"
$runtimeRoot = Join-Path $projectRoot "runtime"
$logRoot = Join-Path $runtimeRoot "logs"
$pidPath = Join-Path $runtimeRoot "api.pid"

if (-not (Test-Path -LiteralPath $envPath)) {
    & (Join-Path $PSScriptRoot "init.ps1")
}

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
Push-Location $projectRoot
try {
    docker compose --env-file .env up -d

    $condaInfo = conda env list --json | ConvertFrom-Json
    $environmentPath = $condaInfo.envs | Where-Object {
        (Split-Path -Leaf $_) -eq "infrasentinel"
    } | Select-Object -First 1
    if (-not $environmentPath) { throw "Conda environment 'infrasentinel' was not found." }
    $pythonPath = Join-Path $environmentPath "python.exe"
    $npmPath = Join-Path $environmentPath "npm.cmd"
    Push-Location (Join-Path $projectRoot "frontend")
    try {
        & $npmPath ci
        & $npmPath run build
    } finally {
        Pop-Location
    }
    & $pythonPath -m alembic upgrade head

    if (Test-Path -LiteralPath $pidPath) {
        $oldPid = [int](Get-Content -Raw -LiteralPath $pidPath)
        if (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {
            Write-Host "API is already running (PID $oldPid)."
            exit 0
        }
    }

    $process = Start-Process -FilePath $pythonPath -ArgumentList @(
        "-m", "uvicorn", "infrasentinel.main:app",
        "--app-dir", "src", "--host", "0.0.0.0", "--port", "8090"
    ) -RedirectStandardOutput (Join-Path $logRoot "api.out.log") `
      -RedirectStandardError (Join-Path $logRoot "api.err.log") `
      -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding ascii
    Write-Host "InfraSentinel API started (PID $($process.Id))."
} finally {
    Pop-Location
}
