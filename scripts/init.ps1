[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"

if (Test-Path -LiteralPath $envPath) {
    Write-Host ".env already exists; leaving it unchanged."
    exit 0
}

function New-RandomSecret([int]$byteCount = 32) {
    $bytes = New-Object byte[] $byteCount
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$dbPassword = New-RandomSecret 24
$redisPassword = New-RandomSecret 24
$minioPassword = New-RandomSecret 24
$appSecret = New-RandomSecret 48

$content = @"
INFRASENTINEL_ENV=development
INFRASENTINEL_SECRET_KEY=$appSecret
DATABASE_URL=postgresql+psycopg://infrasentinel:$dbPassword@127.0.0.1:5432/infrasentinel
POSTGRES_USER=infrasentinel
POSTGRES_PASSWORD=$dbPassword
POSTGRES_DB=infrasentinel
REDIS_PASSWORD=$redisPassword
REDIS_URL=redis://:$redisPassword@127.0.0.1:6379/0
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MINIO_ROOT_USER=infrasentinel
MINIO_ROOT_PASSWORD=$minioPassword
STORAGE_ROOT=runtime/storage
STORAGE_WARNING_GB=900
"@

$utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($envPath, $content, $utf8NoBom)
Write-Host "Created .env with random local secrets."
