[CmdletBinding()]
param(
  [string]$FrontendOrigin = "http://localhost:3000",
  [string]$ApiOrigin = "http://localhost:8000",
  [string]$FrontendHost = "0.0.0.0",
  [string]$GatewayHost = "0.0.0.0",
  [string]$ServiceHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$localEnvPath = Join-Path $root ".local\public-demo.env.ps1"
$logDir = Join-Path $root ".local\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$statePath = Join-Path $root ".local\services.json"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (Test-Path $localEnvPath) {
  . $localEnvPath
}

if ($FrontendOrigin -eq "http://localhost:3000" -and $env:PUBLIC_FRONTEND_ORIGIN) {
  $FrontendOrigin = $env:PUBLIC_FRONTEND_ORIGIN
}

if ($ApiOrigin -eq "http://localhost:8000" -and $env:PUBLIC_API_ORIGIN) {
  $ApiOrigin = $env:PUBLIC_API_ORIGIN
}

if (-not (Test-Path $python)) {
  throw "Missing Python virtual environment at $python"
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm command not found"
}

if (Test-Path $statePath) {
  try {
    $prevState = Get-Content $statePath -Raw | ConvertFrom-Json
    $prev = if ($prevState.services) { @($prevState.services) } else { @($prevState) }
    foreach ($p in $prev) {
      if ($p.pid) {
        Stop-Process -Id ([int]$p.pid) -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {
    # Ignore malformed state file.
  }
}

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

$ahmnSeedMode = if ($env:AHMN_SEED_MODE) { $env:AHMN_SEED_MODE } else { "seeded" }
$frontendCors = @(
  $FrontendOrigin
  "http://localhost:3000"
  "http://127.0.0.1:3000"
) | Where-Object { $_ } | Select-Object -Unique
$corsValue = ($frontendCors -join ",")

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
    pid = $proc.Id
    out = $out
    err = $err
  }
}

$procs = @()
$procs += Start-ServiceProcess -Name "ahmn" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; `$env:REDIS_HOST='localhost'; `$env:REDIS_PORT='6379'; `$env:REDIS_DB='0'; `$env:REDIS_PASSWORD='docai_redis_secret'; `$env:AHMN_SEED_MODE='$ahmnSeedMode'; `$env:HF_HUB_OFFLINE='1'; `$env:TRANSFORMERS_OFFLINE='1'; & '$python' scripts/run_uvicorn_win.py --app ahmn_core.main:app --host $ServiceHost --port 8001"

$procs += Start-ServiceProcess -Name "guardrails" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; `$env:HF_HUB_OFFLINE='1'; `$env:TRANSFORMERS_OFFLINE='1'; & '$python' scripts/run_uvicorn_win.py --app guardrails.main:app --host $ServiceHost --port 8002"

$procs += Start-ServiceProcess -Name "xai_hitl" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; & '$python' scripts/run_uvicorn_win.py --app xai_hitl.main:app --host $ServiceHost --port 8003"

$procs += Start-ServiceProcess -Name "idpo" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; `$env:AHMN_SERVICE_URL='http://$ServiceHost:8001'; `$env:GUARDRAILS_SERVICE_URL='http://$ServiceHost:8002'; `$env:XAI_HITL_SERVICE_URL='http://$ServiceHost:8003'; & '$python' scripts/run_uvicorn_win.py --app idpo.ui.app:app --host $ServiceHost --port 8004"

$procs += Start-ServiceProcess -Name "gateway" -WorkDir $root -InnerCommand `
  "`$env:POSTGRES_URI='postgresql://user:password@localhost:5432/ahmn_db'; `$env:REDIS_URL='redis://:docai_redis_secret@localhost:6379/1'; `$env:AHMN_SERVICE_URL='http://$ServiceHost:8001'; `$env:GUARDRAILS_SERVICE_URL='http://$ServiceHost:8002'; `$env:XAI_HITL_SERVICE_URL='http://$ServiceHost:8003'; `$env:IDPO_SERVICE_URL='http://$ServiceHost:8004'; `$env:IDPO_PROXY_TIMEOUT='1200'; `$env:BACKEND_CORS_ORIGINS='$corsValue'; & '$python' scripts/run_uvicorn_win.py --app gateway.main:app --host $GatewayHost --port 8000"

$procs += Start-ServiceProcess -Name "frontend" -WorkDir (Join-Path $root "frontend") -InnerCommand `
  "`$env:NEXT_PUBLIC_API_URL='$ApiOrigin'; `$env:INTERNAL_API_URL='http://127.0.0.1:8000'; `$env:HOSTNAME='$FrontendHost'; npm run dev -- --hostname $FrontendHost --port 3000"

$state = [PSCustomObject]@{
  deployment_mode = "single_host_public_demo"
  frontend_origin = $FrontendOrigin
  api_origin = $ApiOrigin
  local_env_path = $localEnvPath
  frontend_host = $FrontendHost
  gateway_host = $GatewayHost
  service_host = $ServiceHost
  started_at = (Get-Date).ToString("o")
  services = $procs
}

$state | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath

Write-Output "Started public demo stack."
Write-Output "Frontend origin: $FrontendOrigin"
Write-Output "API origin: $ApiOrigin"
Write-Output ""
$procs | Format-Table -AutoSize
