param([ValidateRange(1024,65535)][int]$Port = 8015)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$databaseUrl = 'postgresql://cnc_local@127.0.0.1:55444/cnc_local'
$cloudflared = Get-Command cloudflared -CommandType Application -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    throw 'cloudflared was not found in PATH. Install it or add its directory to PATH, then reopen the terminal.'
}
$origin = "http://127.0.0.1:$Port"
try {
    $null = Invoke-WebRequest "$origin/openapi.json" -UseBasicParsing -TimeoutSec 5
}
catch {
    $postgresCtl = 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe'
    if (-not (Test-Path $postgresCtl)) {
        throw "Local application is unavailable at $origin and PostgreSQL 18 pg_ctl was not found. Start PostgreSQL and the application using docs/local-quick-tunnel.md. Details: $($_.Exception.Message)"
    }
    $pgStatus = & $postgresCtl -D (Join-Path $projectRoot 'tmp/pg-local-20261109') status 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Starting the documented isolated PostgreSQL database...'
        & $postgresCtl -D (Join-Path $projectRoot 'tmp/pg-local-20261109') -l (Join-Path $projectRoot 'tmp/pg-local-20261109.log') -o '-h 127.0.0.1 -p 55444' start
        if ($LASTEXITCODE -ne 0) { throw 'Could not start the local PostgreSQL database. Check tmp/pg-local-20261109.log.' }
    }
    $python = Join-Path $projectRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path $python)) { throw "Project Python environment was not found: $python" }
    $stdoutLog = Join-Path $projectRoot 'tmp/run-local.out.log'
    $stderrLog = Join-Path $projectRoot 'tmp/run-local.err.log'
    Write-Host "Local application is unavailable at $origin. Starting it in the background. Logs: $stdoutLog and $stderrLog"
    $postgresBin = 'C:\Program Files\PostgreSQL\18\bin'
    if (Test-Path (Join-Path $postgresBin 'libpq.dll')) {
        $env:PSYCOPG_IMPL = 'python'
        $env:PATH = $postgresBin + ';' + $env:PATH
    }
    $env:DATABASE_URL = $databaseUrl
    $serverArgs = @('-m', 'uvicorn', 'backend.local:app', '--host', '127.0.0.1', '--port', "$Port", '--workers', '1', '--ws-max-size', '16384', '--no-proxy-headers')
    $server = Start-Process -FilePath $python -ArgumentList $serverArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        if ($server.HasExited) { break }
        try {
            $null = Invoke-WebRequest "$origin/openapi.json" -UseBasicParsing -TimeoutSec 2
            $ready = $true
            break
        }
        catch { }
    }
    if (-not $ready) {
        $server.Refresh()
        if ($server.HasExited) {
            $details = Get-Content $stderrLog -Tail 15 -ErrorAction SilentlyContinue | Out-String
            throw "Local application exited during startup. Review $stderrLog. $details"
        }
        throw "Local application did not become ready within 30 seconds. Review $stdoutLog and $stderrLog."
    }
    Write-Host "Local application is ready at $origin. Starting Quick Tunnel."
}
Write-Host 'Share the HTTPS trycloudflare.com URL printed below with test devices.'
Write-Host 'This temporarily exposes the test application. Stop with Ctrl+C when finished.'
& $cloudflared.Source tunnel --url $origin --no-autoupdate
if ($LASTEXITCODE -ne 0) { throw 'Quick Tunnel exited with an error.' }
