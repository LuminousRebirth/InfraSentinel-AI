[CmdletBinding()]
param([string]$BaseUrl = "http://127.0.0.1:8090")

$ErrorActionPreference = "Stop"
$result = Invoke-RestMethod -Uri "$BaseUrl/api/v1/health/ready" -TimeoutSec 10
$result | ConvertTo-Json -Depth 5
