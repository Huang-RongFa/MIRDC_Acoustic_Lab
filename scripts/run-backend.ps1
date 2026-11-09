param([string]$DatabaseUrl = $env:DATABASE_URL, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
if (-not $DatabaseUrl) { throw '請設定 DATABASE_URL 或傳入 -DatabaseUrl。' }
$projectRoot = Split-Path $PSScriptRoot -Parent
$env:DATABASE_URL = $DatabaseUrl
# Native psycopg wheels can be blocked by Windows application control.
$postgresBin = 'C:\Program Files\PostgreSQL\18\bin'
if (Test-Path (Join-Path $postgresBin 'libpq.dll')) {
    $env:PSYCOPG_IMPL = 'python'
    $env:PATH = $postgresBin + ';' + $env:PATH
}
Push-Location $projectRoot
try { & ./.venv/Scripts/python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port $Port --workers 1 --ws-max-size 16384 }
finally { Pop-Location }
