$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root ".local\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$statePath = Join-Path $root ".local\services.json"

# Stop previously tracked processes, if any.
if (Test-Path $statePath) {
  try {
    $prev = Get-Content $statePath -Raw | ConvertFrom-Json
    foreach ($p in @($prev)) {
      if ($p.pid) {
        Stop-Process -Id ([int]$p.pid) -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {
    # Ignore malformed state file.
  }
}

# Free expected ports if already in use.
$ports = 3000, 8000, 8001, 8002, 8003, 8004
foreach ($p in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
  if ($conns) {
    $conns | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
      if ($_ -and $_ -ne 0) {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
      }
    }
  }
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$ahmnSeedMode = if ($env:AHMN_SEED_MODE) { $env:AHMN_SEED_MODE } else { "seeded" }

function Start-ServiceProcess {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [Parameter(Mandatory = $true)][string]$InnerCommand
  )

  $out = Join-Path $logDir "$Name.out.log"
  $err = Join-Path $logDir "$Name.err.log"
  if (Test-Path $out) { Remove-Item $out -Force -ErrorAction SilentlyContinue }
  if (Test-Path $err) { Remove-Item $err -Force -ErrorAction SilentlyContinue }

  $proc = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile", "-Command", "Set-Location '$WorkDir'; $InnerCommand" `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err `
    -PassThru

  [PSCustomObject]@{
    name = $Name
    pid  = $proc.Id
    out  = $out
    err  = $err
  }
}

$procs = @()
$procs += Start-ServiceProcess -Name "ahmn" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; `$env:REDIS_HOST='localhost'; `$env:REDIS_PORT='6379'; `$env:REDIS_DB='0'; `$env:REDIS_PASSWORD='docai_redis_secret'; `$env:AHMN_SEED_MODE='$ahmnSeedMode'; & '$python' scripts/run_uvicorn_win.py --app ahmn_core.main:app --host 127.0.0.1 --port 8001"

$procs += Start-ServiceProcess -Name "guardrails" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; & '$python' scripts/run_uvicorn_win.py --app guardrails.main:app --host 127.0.0.1 --port 8002"

$procs += Start-ServiceProcess -Name "xai_hitl" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; & '$python' scripts/run_uvicorn_win.py --app xai_hitl.main:app --host 127.0.0.1 --port 8003"

$procs += Start-ServiceProcess -Name "idpo" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; `$env:AHMN_SERVICE_URL='http://localhost:8001'; `$env:GUARDRAILS_SERVICE_URL='http://localhost:8002'; `$env:XAI_HITL_SERVICE_URL='http://localhost:8003'; & '$python' scripts/run_uvicorn_win.py --app idpo.ui.app:app --host 127.0.0.1 --port 8004"

$procs += Start-ServiceProcess -Name "gateway" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; `$env:REDIS_URL='redis://:docai_redis_secret@localhost:6379/1'; `$env:AHMN_SERVICE_URL='http://localhost:8001'; `$env:GUARDRAILS_SERVICE_URL='http://localhost:8002'; `$env:XAI_HITL_SERVICE_URL='http://localhost:8003'; `$env:IDPO_SERVICE_URL='http://localhost:8004'; `$env:IDPO_PROXY_TIMEOUT='1200'; `$env:BACKEND_CORS_ORIGINS='http://localhost:3000,http://127.0.0.1:3000'; & '$python' scripts/run_uvicorn_win.py --app gateway.main:app --host 127.0.0.1 --port 8000"

$procs += Start-ServiceProcess -Name "frontend" -WorkDir (Join-Path $root "frontend") -InnerCommand `
  "`$env:NEXT_PUBLIC_API_URL='http://localhost:8000'; npm run dev -- --hostname 127.0.0.1 --port 3000"

$procs | ConvertTo-Json -Depth 3 | Set-Content -Path $statePath

$procs | Format-Table -AutoSize
