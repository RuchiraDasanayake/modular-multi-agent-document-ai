#Requires -Version 5.1
<#
.SYNOPSIS
    One-time setup for IDPO research system.
    Run this once after cloning. Then use start.ps1 to launch daily.
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  IDPO Research System - First-Time Setup  " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Check Python 3.10 ──────────────────────────────────────────────────────
Write-Host "[1/5] Checking Python 3.10..." -ForegroundColor Yellow

$pythonExe = $null
foreach ($candidate in @("python", "python3", "python3.10")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python 3\.10") {
            $pythonExe = $candidate
            break
        }
    } catch { }
}

if (-not $pythonExe) {
    Write-Host ""
    Write-Host "  ERROR: Python 3.10 not found." -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/release/python-31011/" -ForegroundColor Red
    Write-Host "  NOTE: PaddleOCR requires exactly Python 3.10 — do NOT use 3.11/3.12/3.13" -ForegroundColor Red
    exit 1
}
Write-Host "  Found: $(&$pythonExe --version)" -ForegroundColor Green

# ── 2. Create .venv ───────────────────────────────────────────────────────────
Write-Host "[2/5] Setting up Python virtual environment..." -ForegroundColor Yellow

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "  Creating .venv with $pythonExe..."
    & $pythonExe -m venv (Join-Path $root ".venv")
    Write-Host "  Installing dependencies (this takes ~10 min on first run)..."
    & $venvPython -m pip install --upgrade pip --quiet
    & $venvPython -m pip install -r (Join-Path $root "requirements.txt") --quiet
    & $venvPython -m pip install -e $root --quiet
    Write-Host "  Python environment ready." -ForegroundColor Green
} else {
    Write-Host "  .venv already exists — checking packages..."
    & $venvPython -m pip install -r (Join-Path $root "requirements.txt") --quiet
    & $venvPython -m pip install -e $root --quiet
    Write-Host "  Packages up to date." -ForegroundColor Green
}

# ── 3. Check Tesseract ────────────────────────────────────────────────────────
Write-Host "[3/5] Checking Tesseract OCR..." -ForegroundColor Yellow

try {
    $tessVer = & tesseract --version 2>&1
    Write-Host "  Found: $($tessVer[0])" -ForegroundColor Green
} catch {
    Write-Host "  WARNING: Tesseract not found in PATH." -ForegroundColor Yellow
    Write-Host "  PaddleOCR is primary — Tesseract is only a fallback." -ForegroundColor Yellow
    Write-Host "  Install from: https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Yellow
}

# ── 4. Frontend Node deps ─────────────────────────────────────────────────────
Write-Host "[4/5] Installing frontend dependencies..." -ForegroundColor Yellow

$frontendDir = Join-Path $root "frontend"
$nodeModules  = Join-Path $frontendDir "node_modules"
if (-not (Test-Path $nodeModules)) {
    Push-Location $frontendDir
    npm install --silent
    Pop-Location
    Write-Host "  Frontend packages installed." -ForegroundColor Green
} else {
    Write-Host "  node_modules already present." -ForegroundColor Green
}

# ── 5. Check Ollama + model ───────────────────────────────────────────────────
Write-Host "[5/5] Checking Ollama and qwen3.5:9b model..." -ForegroundColor Yellow

try {
    $ollamaVer = & ollama --version 2>&1
    Write-Host "  Ollama: $ollamaVer" -ForegroundColor Green

    $models = & ollama list 2>&1
    if ($models -match "qwen3\.5:9b") {
        Write-Host "  qwen3.5:9b already downloaded." -ForegroundColor Green
    } else {
        Write-Host "  Pulling qwen3.5:9b (~6.6 GB — this will take a while)..." -ForegroundColor Yellow
        & ollama pull qwen3.5:9b
        Write-Host "  Model ready." -ForegroundColor Green
    }
} catch {
    Write-Host "  WARNING: Ollama not found." -ForegroundColor Yellow
    Write-Host "  Download from: https://ollama.com" -ForegroundColor Yellow
    Write-Host "  Then run: ollama pull qwen3.5:9b" -ForegroundColor Yellow
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Setup complete!                          " -ForegroundColor Green
Write-Host "  Run start.ps1 to launch the system.     " -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Download CORD dataset into datasets/derived/ (see SETUP.md)" -ForegroundColor White
Write-Host "  2. Double-click or run: .\start.ps1" -ForegroundColor White
Write-Host "  3. Open http://localhost:3000" -ForegroundColor White
Write-Host ""
