#requires -Version 7.2
param([Parameter(Mandatory)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native_recovery_guard.ps1')
. (Join-Path $PSScriptRoot 'native_recovery_passive_common.ps1')
Assert-NativeWindows
$config = Get-NativeConfig -ConfigPath $ConfigPath -CheckFiles
Assert-PassiveRecoveryConfig $config
if (Get-NativeState -Config $config) { throw 'Recovery already has process state; inspect and stop it before restarting.' }
$check = & $config.pythonPath (Join-Path $PSScriptRoot 'native_recovery_files.py') verify-restore --destination $config.runtimeRoot
if ($LASTEXITCODE -ne 0) { throw 'First-start recovery inventory verification failed.' }
Assert-NativeFrontendBuild -Config $config
foreach ($port in @($config.postgresPort, $config.gatewayPort, $config.frontendPort)) { Assert-NativePortFree $port }
New-Item -ItemType Directory -Path $config.logDir, (Split-Path -Parent $config.statePath) -Force | Out-Null
$state = @{ version = 3; frontendMode = 'production'; services = @{}; signature = '' }
$pgCtl = Join-Path $config.pgBin 'pg_ctl.exe'
$args = @('-D', $config.pgData, '-l', (Join-Path $config.logDir 'postgres.server.log'),
  '-o', "-h 127.0.0.1 -p $($config.postgresPort) -c max_logical_replication_workers=0 -c max_worker_processes=0",
  '-w', '-t', '30', 'start')
$pg = Start-RecoveryChild -Executable $pgCtl -Arguments $args -WorkingDirectory $config.runtimeRoot `
  -LogDirectory $config.logDir -Name 'pgctl-start' -Environment @{}
if (-not $pg.WaitForExit(40000) -or $pg.ExitCode -ne 0) { throw 'Recovery PostgreSQL startup failed; inspect private logs.' }
$pg.Dispose()
$pgPid = [int](Get-Content -LiteralPath (Join-Path $config.pgData 'postmaster.pid') -TotalCount 1)
$identity = Get-NativeProcessIdentity -Id $pgPid
if (-not $identity -or $identity.executable -ine (Join-Path $config.pgBin 'postgres.exe') -or
    -not (Test-NativePortOwnership -Port $config.postgresPort -Identity $identity)) {
  throw 'Recovery PostgreSQL process identity did not verify.'
}
$state.services.postgres = $identity
Save-NativeState -Config $config -State $state

$gatewayEnv = @{
  POSTGRES_URI = [string]$config.databaseUrl; JWT_SECRET_KEY = [string]$config.jwtSecret
  ADMIN_PASSWORD = [string]$config.adminPassword; ADMIN_USERNAME = [string]$config.adminUsername
  REQUIRE_EXPLICIT_SECRETS = 'true'; TOKEN_REVOCATION_BACKEND = 'postgresql'; PUBLIC_SIGNUP_ENABLED = 'false'
  BACKEND_CORS_ORIGINS = "http://127.0.0.1:$($config.frontendPort)"; PYTHONUTF8 = '1'
  # Unused research proxies must never resolve to original local services.
  AHMN_SERVICE_URL = 'http://127.0.0.1:1'; GUARDRAILS_SERVICE_URL = 'http://127.0.0.1:1'
  XAI_HITL_SERVICE_URL = 'http://127.0.0.1:1'; IDPO_SERVICE_URL = 'http://127.0.0.1:1'
}
$gateway = Start-RecoveryChild -Executable $config.gatewayPythonPath `
  -Arguments @('scripts\run_uvicorn_win.py', '--app', 'scripts.native_recovery_gateway:app', '--host', '127.0.0.1',
    '--port', [string]$config.gatewayPort) -WorkingDirectory $config.repoRoot -LogDirectory $config.logDir `
  -Name 'gateway' -Environment $gatewayEnv
$state.services.gateway = Get-NativeProcessIdentity -Id $gateway.Id
if (-not $state.services.gateway -or $state.services.gateway.executable -ine $config.gatewayPythonPath) {
  throw 'Recovery gateway process identity did not verify.'
}
Save-NativeState -Config $config -State $state
if (-not (Wait-NativeHttpHealth -Port $config.gatewayPort -Path '/health' -ExpectedStatus 'healthy' `
    -Identity $state.services.gateway -Seconds 45)) { throw 'Recovery gateway health check failed.' }

$frontendEnv = @{
  IDPO_DATA_DIR = [string]$config.dataDir; INTERNAL_API_URL = "http://127.0.0.1:$($config.gatewayPort)"
  NEXT_PUBLIC_API_URL = "http://127.0.0.1:$($config.gatewayPort)"; NODE_ENV = 'production'
  IDPO_NATIVE_FRONTEND = '1'; NEXT_TELEMETRY_DISABLED = '1'; PRODUCT_EXECUTION_MODE = 'postgres'
  IDPO_RECOVERY_READ_ONLY = '1'
  PRODUCT_QUEUE_DATABASE_URL = [string]$config.databaseUrl; IDPO_PRODUCT_PYTHON = [string]$config.pythonPath
  IDPO_AUTO_MODEL = ''; IDPO_AUTO_API_BASE_URL = ''; ICORE_API_KEY = ''; OPENAI_API_KEY = ''
}
$nextCli = Join-Path $config.repoRoot 'frontend\node_modules\next\dist\bin\next'
$frontend = Start-RecoveryChild -Executable $config.nodePath `
  -Arguments @($nextCli, 'start', '--hostname', '127.0.0.1', '--port', [string]$config.frontendPort) `
  -WorkingDirectory (Join-Path $config.repoRoot 'frontend') -LogDirectory $config.logDir -Name 'frontend' `
  -Environment $frontendEnv
$state.services.frontend = Get-NativeProcessIdentity -Id $frontend.Id
if (-not $state.services.frontend -or $state.services.frontend.executable -ine $config.nodePath) {
  throw 'Recovery frontend process identity did not verify.'
}
Save-NativeState -Config $config -State $state
if (-not (Wait-NativeHttpHealth -Port $config.frontendPort -Path '/api/health' -ExpectedStatus 'ok' `
    -Identity $state.services.frontend -Seconds 120)) { throw 'Recovery frontend health check failed.' }
Write-Output 'Passive recovery stack started. No extraction worker was started. Run the authenticated readback drill next.'
