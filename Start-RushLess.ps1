$ErrorActionPreference = 'Stop'
$workspace = $PSScriptRoot
$logs = Join-Path $workspace 'data/private/server-logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$apiHealthy = $false
try { $apiHealthy = (Invoke-RestMethod 'http://127.0.0.1:8001/api/health' -TimeoutSec 3).status -eq 'ok' } catch { }
if (-not $apiHealthy) {
    if (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8001 is occupied by an unresponsive service. Stop this workspace server before restarting; no unrelated process was stopped.' }
    $env:RUSHLESS_DATA_MODE = 'schedule'
    $python = Join-Path $workspace 'backend/.venv/Scripts/python.exe'
    $backend = Join-Path $workspace 'backend'
    Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--app-dir',('"' + $backend + '"'),'--host','127.0.0.1','--port','8001','--no-access-log') -WorkingDirectory $workspace -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'api.out.log') -RedirectStandardError (Join-Path $logs 'api.error.log') | Out-Null
}
if (-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) {
    $frontend = Join-Path $workspace 'frontend'
    if (-not (Test-Path -LiteralPath (Join-Path $frontend '.next/BUILD_ID'))) { throw 'Build the frontend first: cd frontend; npm run build' }
    $node = (Get-Command node).Source
    $next = Join-Path $frontend 'node_modules/next/dist/bin/next'
    Start-Process -FilePath $node -ArgumentList @(('"' + $next + '"'),'start','--hostname','127.0.0.1') -WorkingDirectory $frontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'frontend.out.log') -RedirectStandardError (Join-Path $logs 'frontend.error.log') | Out-Null
}
Write-Host 'RushLess: http://127.0.0.1:3000'
Write-Host 'API health: http://127.0.0.1:8001/api/health'
Write-Host "Local server logs: $logs"
