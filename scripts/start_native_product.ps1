#requires -Version 7.2
param(
  [Parameter(Mandatory)][string]$ConfigPath,
  [switch]$Status
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native_product_common.ps1')
Assert-NativeWindows
$config = Get-NativeConfig -ConfigPath $ConfigPath -CheckFiles:(-not $Status)
$state = Get-NativeState -Config $config

if ($Status) {
  $summary = Get-NativeSummary -Config $config -State $state
  [pscustomobject]@{
    config = $config.configPath
    frontendUrl = "http://127.0.0.1:$($config.frontendPort)"
    services = $summary
  } | ConvertTo-Json -Depth 5
  exit 0
}

if ($state) {
  $summary = Get-NativeSummary -Config $config -State $state
  if ($summary.postgres.portOwned -and $summary.gateway.portOwned -and $summary.frontend.portOwned -and
    (Wait-NativeHttpHealth -Port $config.gatewayPort -Path '/health' -ExpectedStatus 'healthy' `
      -Identity $state.services.gateway -Seconds 3) -and
    (Wait-NativeHttpHealth -Port $config.frontendPort -Path '/api/health' -ExpectedStatus 'ok' `
      -Identity $state.services.frontend -Seconds 3)) {
    Write-Output "Native product already running at http://127.0.0.1:$($config.frontendPort)"
    exit 0
  }
  throw "Native product has partial or stale process state. Inspect status, then use stop_native_product.ps1 before restarting. State: $($config.statePath)"
}

foreach ($port in @($config.postgresPort, $config.gatewayPort, $config.frontendPort)) {
  Assert-NativePortFree -Port $port
}

New-Item -ItemType Directory -Path $config.runtimeRoot, $config.dataDir, $config.logDir,
  (Split-Path -Parent $config.statePath) -Force | Out-Null
$state = @{ version = 1; services = @{ }; signature = '' }

$pgCtl = Join-Path $config.pgBin 'pg_ctl.exe'
$postgresExe = [IO.Path]::GetFullPath((Join-Path $config.pgBin 'postgres.exe'))
$pgLog = Join-Path $config.logDir 'postgres.server.log'
$pgArgs = @('-D', $config.pgData, '-l', $pgLog, '-o', "-h 127.0.0.1 -p $($config.postgresPort)",
  '-w', '-t', '30', 'start')
$quotedPgArgs = ($pgArgs | ForEach-Object { Quote-NativeArgument $_ }) -join ' '
$pgControl = Start-Process -FilePath $pgCtl -ArgumentList $quotedPgArgs -WorkingDirectory $config.runtimeRoot `
  -RedirectStandardOutput (Join-Path $config.logDir 'pgctl-start.out.log') `
  -RedirectStandardError (Join-Path $config.logDir 'pgctl-start.err.log') `
  -WindowStyle Hidden -PassThru
if (-not $pgControl.WaitForExit(40000)) {
  throw "PostgreSQL control timed out. See $($config.logDir)\pgctl-start.err.log"
}
if ($pgControl.ExitCode -ne 0) {
  throw "PostgreSQL did not start. See $($config.logDir)\pgctl-start.err.log"
}
$postmasterPidPath = Join-Path $config.pgData 'postmaster.pid'
if (-not (Test-Path -LiteralPath $postmasterPidPath -PathType Leaf)) {
  throw 'PostgreSQL started without a postmaster.pid file. Refusing to start the application.'
}
$postgresPid = [int](Get-Content -LiteralPath $postmasterPidPath -TotalCount 1)
$postgresIdentity = Get-NativeProcessIdentity -Id $postgresPid
if (-not $postgresIdentity -or $postgresIdentity.executable -ine $postgresExe -or
  -not (Test-NativePortOwnership -Port $config.postgresPort -Identity $postgresIdentity)) {
  throw 'PostgreSQL identity or loopback port could not be verified.'
}
$state.services.postgres = $postgresIdentity
Save-NativeState -Config $config -State $state

try {
  $gatewayEnvironment = @{
    POSTGRES_URI = [string]$config.databaseUrl
    JWT_SECRET_KEY = [string]$config.jwtSecret
    ADMIN_PASSWORD = [string]$config.adminPassword
    ADMIN_USERNAME = [string]$config.adminUsername
    REQUIRE_EXPLICIT_SECRETS = 'true'
    TOKEN_REVOCATION_BACKEND = 'postgresql'
    BACKEND_CORS_ORIGINS = "http://127.0.0.1:$($config.frontendPort)"
    PUBLIC_SIGNUP_ENABLED = 'false'
    PYTHONUTF8 = '1'
  }
  $gateway = Start-NativeChild -Executable $config.gatewayPythonPath `
    -Arguments @('scripts\run_uvicorn_win.py', '--app', 'gateway.main:app', '--host', '127.0.0.1',
      '--port', [string]$config.gatewayPort) -WorkingDirectory $config.repoRoot `
    -LogDirectory $config.logDir -Name 'gateway' -Environment $gatewayEnvironment
  $gatewayIdentity = Get-NativeProcessIdentity -Id $gateway.Id
  if (-not $gatewayIdentity -or $gatewayIdentity.executable -ine $config.gatewayPythonPath) {
    throw 'Gateway process identity could not be verified.'
  }
  $state.services.gateway = $gatewayIdentity
  Save-NativeState -Config $config -State $state
  if (-not (Wait-NativeHttpHealth -Port $config.gatewayPort -Path '/health' -ExpectedStatus 'healthy' `
      -Identity $gatewayIdentity -Seconds 45)) {
    throw "Gateway did not become healthy. See $($config.logDir)\gateway.err.log"
  }

  $frontendEnvironment = @{
    IDPO_DATA_DIR = [string]$config.dataDir
    INTERNAL_API_URL = "http://127.0.0.1:$($config.gatewayPort)"
    NEXT_PUBLIC_API_URL = "http://127.0.0.1:$($config.gatewayPort)"
    NODE_ENV = 'development'
    NEXT_TELEMETRY_DISABLED = '1'
  }
  $nextCli = Join-Path $config.repoRoot 'frontend\node_modules\next\dist\bin\next'
  $frontend = Start-NativeChild -Executable $config.nodePath `
    -Arguments @($nextCli, 'dev', '--webpack', '--hostname', '127.0.0.1', '--port',
      [string]$config.frontendPort) -WorkingDirectory (Join-Path $config.repoRoot 'frontend') `
    -LogDirectory $config.logDir -Name 'frontend' -Environment $frontendEnvironment
  $frontendIdentity = Get-NativeProcessIdentity -Id $frontend.Id
  if (-not $frontendIdentity -or $frontendIdentity.executable -ine $config.nodePath) {
    throw 'Frontend process identity could not be verified.'
  }
  $state.services.frontend = $frontendIdentity
  Save-NativeState -Config $config -State $state
  if (-not (Wait-NativeHttpHealth -Port $config.frontendPort -Path '/api/health' -ExpectedStatus 'ok' `
      -Identity $frontendIdentity -Seconds 120)) {
    throw "Frontend did not become healthy. See $($config.logDir)\frontend.err.log"
  }
  Write-Output "Native product ready at http://127.0.0.1:$($config.frontendPort)"
  Write-Output "Logs: $($config.logDir)"
} catch {
  # Keep the signed receipt so the stop script can clean up only these processes.
  throw
}
