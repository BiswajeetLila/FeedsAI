param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Set-Location $Root

if (-not (Test-Path $Python)) {
    Write-Host "Creating local Python environment..."
    python -m venv .venv
}

if (-not $SkipInstall) {
    Write-Host "Installing FeedsAI and PyInstaller into the local environment..."
    & $Python -m pip install -q -e .
    & $Python -m pip install -q pyinstaller
}

Write-Host "Building FeedsAI.exe in dist\FeedsAI..."
& $Python -m PyInstaller `
    --noconfirm `
    --onedir `
    --name FeedsAI `
    --add-data "app\templates;app\templates" `
    --add-data "prompts;prompts" `
    --collect-submodules uvicorn `
    --collect-submodules websockets `
    --collect-submodules httptools `
    app\desktop_launcher.py

Write-Host "Build complete: dist\FeedsAI\FeedsAI.exe"
