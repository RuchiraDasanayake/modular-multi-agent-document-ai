#requires -Version 7.2
# Supporting recovery helpers; the production launcher remains unchanged.
function Assert-PassiveRecoveryConfig {
  param($Config)
  if (-not $Config.ContainsKey('recoveryPassive') -or $Config.recoveryPassive -ne $true -or
      $Config.frontendMode -ne 'production') { throw 'Only a generated passive production configuration is allowed.' }
  Assert-RecoveryPrivate $Config.runtimeRoot
  foreach ($path in @($Config.pgData, $Config.dataDir, $Config.configPath,
      (Join-Path $Config.runtimeRoot 'state'), (Join-Path $Config.runtimeRoot 'logs'))) {
    if (Test-Path -LiteralPath $path) { Assert-RecoveryPrivate $path -Recurse }
  }
  $expectedConfig = Join-Path $Config.runtimeRoot 'passive-config.json'
  if ($Config.configPath -ine $expectedConfig -or $Config.pgData -ine (Join-Path $Config.runtimeRoot 'pgdata') -or
      $Config.dataDir -ine (Join-Path $Config.runtimeRoot 'data')) { throw 'Recovery paths do not match the generated layout.' }
  $receipt = Get-Content -LiteralPath (Join-Path $Config.runtimeRoot 'restore-receipt.json') -Raw | ConvertFrom-Json -AsHashtable
  if ($receipt.kind -ne 'docai_passive_restore' -or $receipt.destination -ine $Config.runtimeRoot -or
      $receipt.config_sha256 -ne (Get-FileHash -LiteralPath $Config.configPath -Algorithm SHA256).Hash.ToLowerInvariant()) {
    throw 'Passive configuration does not match the restoration receipt.'
  }
  foreach ($key in @('icoreApiKey', 'autoModel', 'autoApiBaseUrl', 'maintenanceDatabaseUrl')) {
    if ($Config.ContainsKey($key)) { throw 'Provider or original database settings are forbidden in passive recovery.' }
  }
  foreach ($folder in @($Config.repoRoot, (Join-Path $Config.repoRoot 'frontend'))) {
    # Next and the gateway load dotenv files independently of process environment.
    if (@(Get-ChildItem -LiteralPath $folder -File -Force | Where-Object {
      $_.Name -in @('.env', '.env.local', '.env.production', '.env.production.local')
    }).Count) { throw 'Passive checkout must not contain runtime dotenv files.' }
  }
}

function Start-RecoveryChild {
  param([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory,
    [string]$LogDirectory, [string]$Name, [hashtable]$Environment)
  # Start-NativeChild restores named overrides but otherwise inherits the caller's
  # environment. Clear it here so arbitrary provider keys, NODE_OPTIONS and Python
  # path injection cannot reach the passive stack.
  $saved = @{}
  foreach ($entry in Get-ChildItem Env:) { $saved[$entry.Name] = $entry.Value }
  $allowed = @('SystemRoot', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP',
    'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA',
    'PROGRAMFILES', 'PROGRAMFILES(X86)', 'COMMONPROGRAMFILES', 'NUMBER_OF_PROCESSORS',
    'PROCESSOR_ARCHITECTURE', 'OS')
  try {
    foreach ($key in $saved.Keys) {
      if ($key -notin $allowed) { [Environment]::SetEnvironmentVariable($key, $null, 'Process') }
    }
    return Start-NativeChild -Executable $Executable -Arguments $Arguments -WorkingDirectory $WorkingDirectory `
      -LogDirectory $LogDirectory -Name $Name -Environment $Environment
  } finally {
    foreach ($entry in @(Get-ChildItem Env:)) {
      if (-not $saved.ContainsKey($entry.Name)) { [Environment]::SetEnvironmentVariable($entry.Name, $null, 'Process') }
    }
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
  }
}
