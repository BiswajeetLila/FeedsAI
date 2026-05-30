param(
    [int]$Port = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Url = "http://127.0.0.1:$Port"

function Test-Server {
    try {
        $r = Invoke-WebRequest -Uri "$Url/healthz" -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

Set-Location $Root

if (-not (Test-Path $Python)) {
    Write-Host "Creating local Python environment..."
    python -m venv .venv
}

Write-Host "Checking dependencies..."
& $Python -c "import fastapi, uvicorn, yaml, pydantic, httpx, feedparser, rapidfuzz" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing dependencies..."
    & $Python -m pip install -q -e .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Dependency install failed. Check network access, then rerun FeedsAI.bat."
        exit 1
    }
}

if (-not (Test-Server)) {
    Write-Host "Starting FeedsAI on $Url ..."
    if (-not $NoBrowser) {
        Start-Process "$Url"
    }
    Write-Host "Server window stays open while FeedsAI is running. Close it to stop."
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
    exit $LASTEXITCODE
} else {
    Write-Host "FeedsAI is running: $Url"
    if (-not $NoBrowser) {
        Start-Process "$Url"
    }
}
