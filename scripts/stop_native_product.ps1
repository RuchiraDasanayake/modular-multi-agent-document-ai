#requires -Version 7.0
param([Parameter(Mandatory)][string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native_product_common.ps1')
Assert-NativeWindows
$config = Get-NativeConfig -ConfigPath $ConfigPath
$state = Get-NativeState -Config $config
if (-not $state) {
  Write-Output 'No tracked native product process state exists.'
  exit 0
}

$expectedExecutables = @{
  postgres = [IO.Path]::GetFullPath((Join-Path $config.pgBin 'postgres.exe'))
  gateway = $config.gatewayPythonPath
  frontend = $config.nodePath
}
foreach ($name in @('postgres', 'gateway', 'frontend')) {
  $identity = $state.services[$name]
  if ($identity -and [string]$identity.executable -ine $expectedExecutables[$name]) {
    throw "Tracked $name executable does not match config. No process was stopped."
  }
}

foreach ($name in @('frontend', 'gateway')) {
  $identity = $state.services[$name]
  if ($identity) { [void](Stop-NativeOwnedTree -Identity $identity) }
}

$postgresIdentity = $state.services.postgres
if ($postgresIdentity -and (Test-NativeProcessIdentity $postgresIdentity)) {
  $postmasterPidPath = Join-Path $config.pgData 'postmaster.pid'
  if (-not (Test-Path -LiteralPath $postmasterPidPath -PathType Leaf) -or
    [int](Get-Content -LiteralPath $postmasterPidPath -TotalCount 1) -ne [int]$postgresIdentity.pid) {
    throw 'PostgreSQL data cluster PID does not match the tracked process. Refusing pg_ctl stop.'
  }
  $pgCtl = Join-Path $config.pgBin 'pg_ctl.exe'
  if (-not (Test-Path -LiteralPath $pgCtl -PathType Leaf)) { throw 'pg_ctl.exe is missing.' }
  $pgArgs = @('-D', $config.pgData, '-m', 'fast', '-w', '-t', '30', 'stop')
  $quotedPgArgs = ($pgArgs | ForEach-Object { Quote-NativeArgument $_ }) -join ' '
  $control = Start-Process -FilePath $pgCtl -ArgumentList $quotedPgArgs -WorkingDirectory $config.runtimeRoot `
    -RedirectStandardOutput (Join-Path $config.logDir 'pgctl-stop.out.log') `
    -RedirectStandardError (Join-Path $config.logDir 'pgctl-stop.err.log') `
    -WindowStyle Hidden -PassThru
  if (-not $control.WaitForExit(40000)) { throw "PostgreSQL stop timed out. See $($config.logDir)\pgctl-stop.err.log" }
  if ($control.ExitCode -ne 0) { throw "PostgreSQL did not stop. See $($config.logDir)\pgctl-stop.err.log" }
}

$deadline = (Get-Date).AddSeconds(5)
do {
  $remaining = @(@('frontend', 'gateway', 'postgres') | Where-Object {
    $state.services[$_] -and (Test-NativeProcessIdentity $state.services[$_])
  })
  if ($remaining.Count -eq 0) { break }
  Start-Sleep -Milliseconds 200
} while ((Get-Date) -lt $deadline)
foreach ($name in @('frontend', 'gateway', 'postgres')) {
  if ($state.services[$name] -and (Test-NativeProcessIdentity $state.services[$name])) {
    throw "$name is still running; retained process state for another stop attempt."
  }
}
Remove-Item -LiteralPath $config.statePath -Force
Write-Output 'Tracked native product processes stopped. Runtime data and logs were preserved.'
