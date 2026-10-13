#requires -Version 7.2
param([Parameter(Mandatory)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native_recovery_guard.ps1')
. (Join-Path $PSScriptRoot 'native_recovery_passive_common.ps1')
Assert-NativeWindows
$config = Get-NativeConfig -ConfigPath $ConfigPath -CheckFiles
Assert-PassiveRecoveryConfig $config
if (Get-NativeState -Config $config) { throw 'Build the recovery frontend before starting the passive stack.' }
$check = & $config.pythonPath (Join-Path $PSScriptRoot 'native_recovery_files.py') verify-restore --destination $config.runtimeRoot
if ($LASTEXITCODE -ne 0) { throw 'Restoration verification failed before build.' }
New-Item -ItemType Directory -Path $config.logDir -Force | Out-Null
$child = Start-RecoveryChild -Executable (Join-Path $PSHOME 'pwsh.exe') `
  -Arguments @('-NoProfile', '-File', (Join-Path $PSScriptRoot 'build_native_frontend.ps1'), '-ConfigPath', $ConfigPath) `
  -WorkingDirectory $config.repoRoot -LogDirectory $config.logDir -Name 'recovery-build' `
  -Environment @{ IDPO_RECOVERY_READ_ONLY = '1' }
$identity = Get-NativeProcessIdentity -Id $child.Id
try {
  if (-not $child.WaitForExit(960000)) {
    if ($identity) { [void](Stop-NativeOwnedTree -Identity $identity) }
    throw 'Recovery build timed out. Inspect private logs.'
  }
  if ($child.ExitCode -ne 0) { throw 'Recovery build failed. Inspect private logs.' }
  Assert-NativeFrontendBuild -Config $config
  Write-Output 'Recovery frontend build verified for the clone gateway port.'
} finally { $child.Dispose() }
