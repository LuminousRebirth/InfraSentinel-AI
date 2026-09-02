[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"
$runtimeRoot = Join-Path $projectRoot "runtime"
$logRoot = Join-Path $runtimeRoot "logs"
$pidPath = Join-Path $runtimeRoot "api.pid"
$workerCount = 2

function Test-InfraProcess {
    param([int]$ProcessId, [string]$ExpectedPython, [string]$CommandPattern)
    $running = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" `
        -ErrorAction SilentlyContinue
    return $null -ne $running `
        -and $running.ExecutablePath -eq $ExpectedPython `
        -and $running.CommandLine -match $CommandPattern
}

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
    & $pythonPath -m infrasentinel.cli sync-vision-models
    & $pythonPath -m infrasentinel.cli seed-alert-rules

    $apiRunning = $false
    if (Test-Path -LiteralPath $pidPath) {
        $oldPid = [int](Get-Content -Raw -LiteralPath $pidPath)
        if (Test-InfraProcess $oldPid $pythonPath "uvicorn.*infrasentinel\.main:app") {
            Write-Host "API is already running (PID $oldPid)."
            $apiRunning = $true
        } else {
            Remove-Item -LiteralPath $pidPath -Force
        }
    }

    if (-not $apiRunning) {
        $process = Start-Process -FilePath $pythonPath -ArgumentList @(
            "-m", "uvicorn", "infrasentinel.main:app",
            "--app-dir", "src", "--host", "0.0.0.0", "--port", "8090"
        ) -RedirectStandardOutput (Join-Path $logRoot "api.out.log") `
          -RedirectStandardError (Join-Path $logRoot "api.err.log") `
          -WindowStyle Hidden -PassThru
        Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding ascii
        Write-Host "InfraSentinel API started (PID $($process.Id))."
    }

    for ($index = 1; $index -le $workerCount; $index++) {
        $workerPidPath = Join-Path $runtimeRoot "worker-$index.pid"
        $workerRunning = $false
        if (Test-Path -LiteralPath $workerPidPath) {
            $oldWorkerPid = [int](Get-Content -Raw -LiteralPath $workerPidPath)
            if (Test-InfraProcess $oldWorkerPid $pythonPath "infrasentinel\.worker") {
                Write-Host "Vision worker $index is already running (PID $oldWorkerPid)."
                $workerRunning = $true
            } else {
                Remove-Item -LiteralPath $workerPidPath -Force
            }
        }
        if (-not $workerRunning) {
            $worker = Start-Process -FilePath $pythonPath -ArgumentList @(
                "-m", "infrasentinel.worker"
            ) -RedirectStandardOutput (Join-Path $logRoot "worker-$index.out.log") `
              -RedirectStandardError (Join-Path $logRoot "worker-$index.err.log") `
              -WindowStyle Hidden -PassThru
            Set-Content -LiteralPath $workerPidPath -Value $worker.Id -Encoding ascii
            Write-Host "Vision worker $index started (PID $($worker.Id))."
        }
    }

    $intelligencePidPath = Join-Path $runtimeRoot "intelligence-worker.pid"
    $intelligenceRunning = $false
    if (Test-Path -LiteralPath $intelligencePidPath) {
        $oldIntelligencePid = [int](Get-Content -Raw -LiteralPath $intelligencePidPath)
        if (Test-InfraProcess $oldIntelligencePid $pythonPath "infrasentinel\.intelligence_worker") {
            Write-Host "Intelligence worker is already running (PID $oldIntelligencePid)."
            $intelligenceRunning = $true
        } else {
            Remove-Item -LiteralPath $intelligencePidPath -Force
        }
    }
    if (-not $intelligenceRunning) {
        $intelligenceWorker = Start-Process -FilePath $pythonPath -ArgumentList @(
            "-m", "infrasentinel.intelligence_worker"
        ) -RedirectStandardOutput (Join-Path $logRoot "intelligence-worker.out.log") `
          -RedirectStandardError (Join-Path $logRoot "intelligence-worker.err.log") `
          -WindowStyle Hidden -PassThru
        Set-Content -LiteralPath $intelligencePidPath -Value $intelligenceWorker.Id -Encoding ascii
        Write-Host "Intelligence worker started (PID $($intelligenceWorker.Id))."
    }
} finally {
    Pop-Location
}
