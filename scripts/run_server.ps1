# scripts/run_server.ps1
# Launch FeedsAI uvicorn in its own visible window so you can see live logs.
#
# Usage:
#   .\scripts\run_server.ps1            # foreground in current window
#   .\scripts\run_server.ps1 -Detach    # spawn new PowerShell window, return immediately
#
# The detached window stays open until you Ctrl+C or close it.

param(
    [switch]$Detach
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$python   = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Error "Python venv not found at $python. Run 'uv venv' / 'uv pip install -r requirements.txt' first."
    exit 1
}

# Free port 8000 if something is already bound (stale uvicorn from prior run)
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Port 8000 already bound by PID $($existing.OwningProcess). Stopping it." -ForegroundColor Yellow
    Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

$args = @(
    '-m', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1',
    '--port', '8000',
    '--log-level', 'info'
)

if ($Detach) {
    $title = 'FeedsAI server'
    $cmd   = "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location '$repoRoot'; & '$python' $($args -join ' ')"
    Start-Process powershell -ArgumentList '-NoExit', '-Command', $cmd | Out-Null
    Write-Host "FeedsAI server launched in a new window. Open http://127.0.0.1:8000/" -ForegroundColor Green
    Write-Host "Status:  http://127.0.0.1:8000/status"
    Write-Host "Logs:    http://127.0.0.1:8000/logs   (or tail data\server.log)"
} else {
    Set-Location $repoRoot
    Write-Host "FeedsAI starting at http://127.0.0.1:8000/ - Ctrl+C to stop." -ForegroundColor Green
    & $python @args
}
