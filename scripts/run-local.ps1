param(
    [Parameter(Mandatory=$true)][string]$DatabaseUrl,
    [ValidateRange(1024,65535)][int]$Port = 8015,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    if (-not $SkipBuild) {
        & npm.cmd --prefix frontend run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    }
    $env:DATABASE_URL = $DatabaseUrl
    $postgresBin = 'C:\Program Files\PostgreSQL\18\bin'
    if (Test-Path (Join-Path $postgresBin 'libpq.dll')) {
        $env:PSYCOPG_IMPL = 'python'
        $env:PATH = $postgresBin + ';' + $env:PATH
    }
    Write-Host "Local recording: http://localhost:$Port"
    Write-Host 'Quick Tunnel: run scripts/run-quick-tunnel.ps1 in another terminal.'
    # This testing entry point accepts only loopback connections, including
    # cloudflared. Public forwarded IPs must not become internal-network peers.
    & ./.venv/Scripts/python.exe -m uvicorn backend.local:app --host 127.0.0.1 --port $Port --workers 1 --ws-max-size 16384 --no-proxy-headers
    if ($LASTEXITCODE -ne 0) { throw 'Local server failed; check database/schema and port.' }
}
finally { Pop-Location }
