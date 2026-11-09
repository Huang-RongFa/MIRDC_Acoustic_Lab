param([Parameter(Mandatory=$true)][string]$TestDatabaseUrl)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$env:TEST_DATABASE_URL = $TestDatabaseUrl
$postgresBin = 'C:\Program Files\PostgreSQL\18\bin'
if (Test-Path (Join-Path $postgresBin 'libpq.dll')) {
    $env:PSYCOPG_IMPL = 'python'
    $env:PATH = $postgresBin + ';' + $env:PATH
}
Push-Location $projectRoot
try { & ./.venv/Scripts/python.exe -m pytest backend/tests -q; exit $LASTEXITCODE }
finally { Pop-Location }
