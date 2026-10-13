#requires -Version 7.2
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'native_recovery_guard.ps1')
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'native_recovery_passive_common.ps1')
function Assert-Test([bool]$Condition, [string]$Message) { if (-not $Condition) { throw "FAIL: $Message" } }
function Assert-Throws([scriptblock]$Action, [string]$Message) {
  $failed = $false
  try { & $Action | Out-Null } catch { $failed = $true }
  Assert-Test $failed $Message
}
Assert-NativeWindows
$testRoot = Join-Path $env:TEMP ('docai-recovery-unit-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
  Protect-RecoveryDirectory $testRoot
  $secret = Join-Path $testRoot 'private.json'
  '{}' | Set-Content -LiteralPath $secret
  Assert-RecoveryPrivate $testRoot -Recurse
  $acl = Get-Acl -LiteralPath $secret
  $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    [Security.Principal.SecurityIdentifier]::new('S-1-1-0'), 'Read', 'Allow'))
  Set-Acl -LiteralPath $secret -AclObject $acl
  Assert-Throws { Assert-RecoveryPrivate $testRoot -Recurse } 'A public descendant ACL must be rejected.'
  # Restore fixture inheritance; never touch any runtime input.
  $acl.RemoveAccessRuleAll([Security.AccessControl.FileSystemAccessRule]::new(
    [Security.Principal.SecurityIdentifier]::new('S-1-1-0'), 'Read', 'Allow'))
  Set-Acl -LiteralPath $secret -AclObject $acl
  $target = Join-Path $testRoot 'ordinary'; New-Item -ItemType Directory -Path $target | Out-Null
  $link = Join-Path $testRoot 'junction'
  New-Item -ItemType Junction -Path $link -Target $target | Out-Null
  Assert-Throws { Assert-RecoveryPlainPath (Join-Path $link 'child') } 'A junction ancestor must be rejected.'
  Assert-Throws { Assert-RecoveryPrivate $testRoot -Recurse } 'Private storage cannot hide a junction.'
  Remove-Item -LiteralPath $link

  $env:UNUSUAL_PROVIDER_SECRET = 'fixture-provider-secret'
  $env:NODE_OPTIONS = '--require do-not-load'
  function Start-NativeChild {
    param($Executable, $Arguments, $WorkingDirectory, $LogDirectory, $Name, $Environment)
    Assert-Test (-not $env:UNUSUAL_PROVIDER_SECRET -and -not $env:NODE_OPTIONS) 'All non-OS inherited variables are removed.'
    Assert-Test ([bool]$env:SystemRoot) 'OS environment remains available.'
    return [pscustomobject]@{ Id = 123; marker = 'no-child-started' }
  }
  $child = Start-RecoveryChild -Executable 'fixture.exe' -Arguments @() -WorkingDirectory $testRoot `
    -LogDirectory $testRoot -Name 'fixture' -Environment @{ IDPO_RECOVERY_READ_ONLY = '1' }
  Assert-Test ($child.marker -eq 'no-child-started') 'Only the stub child was invoked.'
  Assert-Test ($env:UNUSUAL_PROVIDER_SECRET -eq 'fixture-provider-secret' -and $env:NODE_OPTIONS -eq '--require do-not-load') 'Parent environment restored.'
  Remove-Item Env:UNUSUAL_PROVIDER_SECRET; Remove-Item Env:NODE_OPTIONS

  # Stopped-state checks are exercised with synthetic identities, never a live database.
  $config = @{ configPath = $secret; pgData = $target; dataDir = $target; repoRoot = 'C:\fixture';
    pythonPath = 'C:\fixture\python.exe'; gatewayPythonPath = 'C:\fixture\gateway.exe'; pgBin = 'C:\fixture\pg';
    nodePath = 'C:\fixture\node.exe';
    postgresPort = 55432; gatewayPort = 8000; frontendPort = 3000 }
  function Get-NativeConfig { param($ConfigPath) return $config }
  function Assert-RecoveryPrivate { param($LiteralPath, [switch]$Recurse) }
  function Get-NativeState { param($Config) return @{ services = @{ frontend = @{ pid = 123 } } } }
  function Test-NativeProcessIdentity { param($Expected) return $true }
  Assert-Throws { Assert-RecoveryStopped $secret } 'Running owned process refuses backup.'
  function Get-NativeState { param($Config) return $null }
  function Assert-NativePortFree { param($Port) throw 'fixture occupied port' }
  Assert-Throws { Assert-RecoveryStopped $secret } 'Occupied port refuses backup even without receipt.'
  function Assert-NativePortFree { param($Port) }
  '123' | Set-Content -LiteralPath (Join-Path $target 'postmaster.pid')
  Assert-Throws { Assert-RecoveryStopped $secret } 'A remaining PID file refuses backup.'
  function Assert-PassiveRecoveryConfig { param($Config) }
  $runningState = @{ services = @{
    postgres = @{ executable = 'C:\fixture\pg\postgres.exe'; pid = 1 }
    gateway = @{ executable = 'C:\fixture\gateway.exe'; pid = 2 }
    frontend = @{ executable = 'C:\fixture\node.exe'; pid = 3 }
  } }
  function Get-NativeState { param($Config) return $runningState }
  function Test-NativePortOwnership { param($Port, $Identity) return $true }
  Assert-RecoveryRunning $secret
  $runningState.services.worker = @{ executable = 'C:\fixture\node.exe'; pid = 4 }
  Assert-Throws { Assert-RecoveryRunning $secret } 'A worker in the passive receipt is rejected.'
  [void]$runningState.services.Remove('worker')
  function Test-NativePortOwnership { param($Port, $Identity) return $false }
  Assert-Throws { Assert-RecoveryRunning $secret } 'Wrong port ownership prevents passive HTTP verification.'
  Write-Output 'PASS: private ACLs, junction rejection, isolated environment, stopped guards and passive process ownership.'
} finally {
  Remove-Item Env:UNUSUAL_PROVIDER_SECRET -ErrorAction SilentlyContinue
  Remove-Item Env:NODE_OPTIONS -ErrorAction SilentlyContinue
  $resolved = [IO.Path]::GetFullPath($testRoot)
  $tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
  if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or
      (Split-Path -Leaf $resolved) -notlike 'docai-recovery-unit-*') { throw 'Unexpected fixture cleanup path.' }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}
