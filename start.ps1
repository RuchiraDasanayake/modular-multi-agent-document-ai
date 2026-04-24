#Requires -Version 5.1
<#
.SYNOPSIS
    Launch IDPO research system (Ollama + frontend).
    Run install.ps1 first on a fresh machine.
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host ""
Write-Host "==============================" -ForegroundColor Cyan
Write-Host "  IDPO Research System        " -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
Write-Host ""

# ── Guard: venv must exist ────────────────────────────────────────────────────
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: .venv not found. Run install.ps1 first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# ── Guard: node_modules must exist ───────────────────────────────────────────
$nodeModules = Join-Path $root "frontend\node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Host "ERROR: frontend/node_modules missing. Run install.ps1 first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# ── 1. Start Ollama if not already running ────────────────────────────────────
Write-Host "[1/2] Checking Ollama..." -ForegroundColor Yellow

$ollamaRunning = $false
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:11434" -TimeoutSec 2 -ErrorAction Stop
    $ollamaRunning = $true
    Write-Host "  Ollama already running." -ForegroundColor Green
} catch { }

if (-not $ollamaRunning) {
    try {
        Write-Host "  Starting Ollama..." -ForegroundColor Yellow
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
        Write-Host "  Ollama started." -ForegroundColor Green
    } catch {
        Write-Host "  WARNING: Could not start Ollama. LLM extraction will fail." -ForegroundColor Yellow
        Write-Host "  Install from https://ollama.com then rerun this script." -ForegroundColor Yellow
    }
}

# ── 2. Start frontend ─────────────────────────────────────────────────────────
Write-Host "[2/2] Starting frontend on http://localhost:3000 ..." -ForegroundColor Yellow

$frontendDir = Join-Path $root "frontend"

# Launch frontend in a new visible window so you can see its output
$frontendProc = Start-Process "powershell.exe" `
    -ArgumentList "-NoProfile", "-Command", `
        "Set-Location '$frontendDir'; `$env:PYTHONUTF8='1'; npm run dev; Read-Host 'Press Enter to close'" `
    -PassThru

Write-Host ""
Write-Host "==============================" -ForegroundColor Green
Write-Host "  System starting up...       " -ForegroundColor Green
Write-Host "  Open: http://localhost:3000  " -ForegroundColor Green
Write-Host "==============================" -ForegroundColor Green
Write-Host ""
Write-Host "Frontend PID: $($frontendProc.Id)" -ForegroundColor Gray
Write-Host "Close the frontend window to stop the system." -ForegroundColor Gray
Write-Host ""

# Open browser after short delay
Start-Sleep -Seconds 5
try {
    Start-Process "http://localhost:3000"
} catch { }

# Keep this window open so user knows what's running
Write-Host "Press Ctrl+C or close this window when done." -ForegroundColor Yellow
Wait-Process -Id $frontendProc.Id -ErrorAction SilentlyContinue
