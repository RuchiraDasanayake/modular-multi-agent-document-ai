#requires -Version 7.2
param([ValidateSet('Protect', 'Private', 'PrivateTree', 'Stopped', 'PassiveRunning')][string]$Action, [string]$Path)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native_product_common.ps1')
. (Join-Path $PSScriptRoot 'native_recovery_passive_common.ps1')

function Get-RecoveryAllowedSids {
  return @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value, 'S-1-5-18', 'S-1-5-32-544')
}

function Assert-RecoveryPlainPath {
  param([string]$LiteralPath)
  if (-not [IO.Path]::IsPathFullyQualified($LiteralPath)) { throw 'Recovery paths must be absolute.' }
  $cursor = [IO.Path]::GetFullPath($LiteralPath)
  while ($cursor) {
    if (Test-Path -LiteralPath $cursor) {
      $item = Get-Item -LiteralPath $cursor -Force
      if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Recovery storage cannot use reparse points.' }
    }
    $cursor = Split-Path -Parent $cursor
  }
}

function Assert-RecoveryPrivate {
  param([string]$LiteralPath, [switch]$Recurse)
  Assert-RecoveryPlainPath $LiteralPath
  $allowed = Get-RecoveryAllowedSids
  $items = @((Get-Item -LiteralPath $LiteralPath -Force))
  if ($Recurse) { $items += @(Get-ChildItem -LiteralPath $LiteralPath -Recurse -Force) }
  foreach ($item in $items) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Private recovery storage contains a reparse point.' }
    $acl = Get-Acl -LiteralPath $item.FullName
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -notin $allowed) { throw 'Unexpected recovery storage owner.' }
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
      if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin $allowed) {
        throw 'Recovery storage grants access outside the operator, SYSTEM and Administrators.'
      }
    }
  }
}

function Protect-RecoveryDirectory {
  param([string]$LiteralPath)
  Assert-RecoveryPlainPath $LiteralPath
  if (-not (Test-Path -LiteralPath $LiteralPath -PathType Container) -or
      @(Get-ChildItem -LiteralPath $LiteralPath -Force).Count -ne 0) {
    throw 'Only a new empty recovery directory can be protected.'
  }
  $acl = [Security.AccessControl.DirectorySecurity]::new()
  $acl.SetAccessRuleProtection($true, $false)
  $acl.SetOwner([Security.Principal.WindowsIdentity]::GetCurrent().User)
  foreach ($sid in Get-RecoveryAllowedSids) {
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
      [Security.Principal.SecurityIdentifier]::new($sid), 'FullControl',
      'ContainerInherit, ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
  }
  Set-Acl -LiteralPath $LiteralPath -AclObject $acl
  Assert-RecoveryPrivate $LiteralPath
}

function Assert-RecoveryStopped {
  param([string]$ConfigPath)
  $config = Get-NativeConfig -ConfigPath $ConfigPath
  Assert-RecoveryPrivate $config.configPath
  foreach ($folder in @($config.pgData, $config.dataDir)) { Assert-RecoveryPrivate $folder }
  $state = Get-NativeState -Config $config
  if ($state) {
    foreach ($identity in $state.services.Values) {
      if (Test-NativeProcessIdentity $identity) { throw 'An owned product process is still running.' }
    }
  }
  foreach ($port in @($config.postgresPort, $config.gatewayPort, $config.frontendPort)) {
    Assert-NativePortFree -Port $port
  }
  if (Test-Path -LiteralPath (Join-Path $config.pgData 'postmaster.pid')) {
    throw 'PostgreSQL PID file remains; do not remove it to bypass the clean-stop check.'
  }
  # Dedicated parser/gateway interpreters may also be used by a benchmark. Refuse
  # that ambiguity: a backup must wait until all users of those runtimes finish.
  $executables = @($config.pythonPath, $config.gatewayPythonPath,
    (Join-Path $config.pgBin 'postgres.exe'))
  $guardParent = (Get-CimInstance Win32_Process -Filter "ProcessId = $PID").ParentProcessId
  $engine = 'native_recovery_files.py'
  foreach ($process in Get-CimInstance Win32_Process) {
    if ($process.ProcessId -eq $guardParent -and $process.CommandLine -and
        $process.CommandLine.Contains($engine, [StringComparison]::OrdinalIgnoreCase)) { continue }
    if ($process.ExecutablePath -and $process.ExecutablePath -in $executables) {
      throw 'A configured PostgreSQL or Python process is still running.'
    }
    if (-not $process.ExecutablePath -and $process.Name -in @('postgres.exe', 'python.exe')) {
      throw 'A possible database/parser process could not be inspected.'
    }
    if ($process.Name -eq 'node.exe') {
      if (-not $process.CommandLine -or $process.CommandLine.Contains($config.repoRoot,
          [StringComparison]::OrdinalIgnoreCase) -or $process.CommandLine -match 'product-execution-worker') {
        throw 'A possible product frontend or extraction worker is still running.'
      }
    }
  }
  $control = Join-Path $config.pgBin 'pg_controldata.exe'
  if (-not (Test-Path -LiteralPath $control -PathType Leaf)) { throw 'pg_controldata.exe is required.' }
  $info = [Diagnostics.ProcessStartInfo]::new($control)
  $info.UseShellExecute = $false; $info.CreateNoWindow = $true
  $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
  $info.Environment['LC_ALL'] = 'C'; $info.Environment['LANG'] = 'C'
  $info.ArgumentList.Add($config.pgData)
  $child = [Diagnostics.Process]::Start($info)
  try {
    $stdout = $child.StandardOutput.ReadToEndAsync()
    $stderr = $child.StandardError.ReadToEndAsync()
    if (-not $child.WaitForExit(10000)) { $child.Kill(); throw 'PostgreSQL control-file check timed out.' }
    if ($child.ExitCode -ne 0 -or $stdout.GetAwaiter().GetResult() -notmatch '(?m)^Database cluster state:\s+shut down\s*$') {
      throw 'PostgreSQL control file does not report a cleanly shut down primary cluster.'
    }
    [void]$stderr.GetAwaiter().GetResult()
  } finally { $child.Dispose() }
}

function Assert-RecoveryRunning {
  param([string]$ConfigPath)
  $config = Get-NativeConfig -ConfigPath $ConfigPath
  Assert-PassiveRecoveryConfig $config
  $state = Get-NativeState -Config $config
  if (-not $state -or $state.services['worker']) { throw 'Passive recovery process receipt is missing or includes a worker.' }
  $expected = @{
    postgres = @((Join-Path $config.pgBin 'postgres.exe'), $config.postgresPort)
    gateway = @($config.gatewayPythonPath, $config.gatewayPort)
    frontend = @($config.nodePath, $config.frontendPort)
  }
  foreach ($name in $expected.Keys) {
    $identity = $state.services[$name]
    if (-not $identity -or $identity.executable -ine $expected[$name][0] -or
        -not (Test-NativePortOwnership -Port $expected[$name][1] -Identity $identity)) {
      throw 'Passive recovery process/port ownership did not verify.'
    }
  }
}

if ($Action) {
  Assert-NativeWindows
  switch ($Action) {
    Protect { Protect-RecoveryDirectory $Path }
    Private { Assert-RecoveryPrivate $Path }
    PrivateTree { Assert-RecoveryPrivate $Path -Recurse }
    Stopped { Assert-RecoveryStopped $Path }
    PassiveRunning { Assert-RecoveryRunning $Path }
  }
}
