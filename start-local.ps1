param([string]$DatabaseUrl = $env:DATABASE_URL, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Missing project .venv\Scripts\python.exe. Set up the project environment first.' }
$npm = Get-Command npm.cmd -ErrorAction Stop
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'))) { throw 'Frontend dependencies missing. Run npm install in frontend first.' }
if (-not $DatabaseUrl) { $DatabaseUrl = 'postgresql://postgres@localhost:5432/cnc_acoustic_lab' }
$env:DATABASE_URL = $DatabaseUrl
$postgresBin = 'C:\Program Files\PostgreSQL\18\bin'
if (Test-Path (Join-Path $postgresBin 'libpq.dll')) { $env:PSYCOPG_IMPL = 'python'; $env:PATH = $postgresBin + ';' + $env:PATH }
Push-Location $projectRoot
try {
    & $python -m backend.schema
    if ($LASTEXITCODE -ne 0) { throw 'Database preflight failed. No migrations were applied. See docs/startup-repair.md.' }
    if ($CheckOnly) { Write-Host 'Preflight passed; no servers started.'; return }
    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    foreach ($port in @(8000,5173)) { if ($listeners.Port -contains $port) { throw "Port $port is occupied. Close the existing server or use its terminal; no process was stopped." } }
    $shell = (Get-Process -Id $PID).Path
    $env:CNC_BACKEND_URL = 'http://127.0.0.1:8000'
    # Credentials are inherited through the environment, never put on a command line.
    $backendCommand = "Set-Location -LiteralPath '$($projectRoot.Replace("'","''"))'; & '.\.venv\Scripts\python.exe' -m uvicorn backend.app:app --reload --reload-dir backend --host 127.0.0.1 --port 8000; Write-Host ('Backend exited: ' + `$LASTEXITCODE)"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($backendCommand))
    $null = Start-Process -FilePath $shell -ArgumentList @('-NoProfile','-NoExit','-EncodedCommand',$encoded) -WorkingDirectory $projectRoot -WindowStyle Normal -PassThru
    $ready = $false
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Seconds 1
        try { $health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if ($health.status -eq 'ok' -and $health.service -eq 'cnc-acoustic-lab') { $ready=$true; break } }
        catch { Write-Verbose $_.Exception.Message }
    }
    if (-not $ready) { throw 'Backend health check failed. The backend PowerShell window remains open with its error. Frontend was not started.' }
    $frontendCommand = "Set-Location -LiteralPath '$((Join-Path $projectRoot 'frontend').Replace("'","''"))'; & npm.cmd run dev -- --strictPort; Write-Host ('Frontend exited: ' + `$LASTEXITCODE)"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($frontendCommand))
    $null = Start-Process -FilePath $shell -ArgumentList @('-NoProfile','-NoExit','-EncodedCommand',$encoded) -WorkingDirectory $projectRoot -WindowStyle Normal -PassThru
    Write-Host 'Backend ready: http://127.0.0.1:8000'
    Write-Host 'Frontend starting: http://localhost:5173/'
    Write-Host 'Reload is for development only. Do not edit backend files during recording. Stop each server with Ctrl+C in its window.'
}
finally { Pop-Location }
