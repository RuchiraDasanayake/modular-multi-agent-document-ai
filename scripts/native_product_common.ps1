#requires -Version 7.2
# Shared, sourceable helpers for the native Windows product launcher.
Set-StrictMode -Version Latest

function Assert-NativeWindows {
  if ($env:OS -ne 'Windows_NT') { throw 'The native product launcher requires Windows.' }
}

function Get-NativeConfig {
  param([Parameter(Mandatory)][string]$ConfigPath, [switch]$CheckFiles)

  if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Native product config is missing: $ConfigPath"
  }
  try { $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json -AsHashtable }
  catch { throw 'Native product config is not valid JSON.' }
  $required = @('repoRoot', 'runtimeRoot', 'pgBin', 'pgData', 'postgresPort', 'databaseUrl',
    'jwtSecret', 'adminPassword', 'dataDir', 'frontendPort', 'gatewayPort', 'pythonPath')
  foreach ($key in $required) {
    if (-not $config.ContainsKey($key) -or [string]::IsNullOrWhiteSpace([string]$config[$key])) {
      throw "Native product config requires $key."
    }
  }
  foreach ($key in @('repoRoot', 'runtimeRoot', 'pgBin', 'pgData', 'dataDir', 'pythonPath')) {
    $value = [string]$config[$key]
    if (-not [IO.Path]::IsPathFullyQualified($value) -or $value -match '["\r\n]') {
      throw "Native product config $key must be an absolute Windows path without quotes or newlines."
    }
    $config[$key] = [IO.Path]::GetFullPath($value).TrimEnd('\')
  }
  if (-not $config.ContainsKey('gatewayPythonPath') -or -not $config.gatewayPythonPath) {
    $config.gatewayPythonPath = $config.pythonPath
  }
  if (-not [IO.Path]::IsPathFullyQualified([string]$config.gatewayPythonPath) -or
    [string]$config.gatewayPythonPath -match '["\r\n]') {
    throw 'Native product config gatewayPythonPath must be an absolute Windows path.'
  }
  $config.gatewayPythonPath = [IO.Path]::GetFullPath([string]$config.gatewayPythonPath).TrimEnd('\')
  foreach ($key in @('postgresPort', 'gatewayPort', 'frontendPort')) {
    $port = 0
    if (-not [int]::TryParse([string]$config[$key], [ref]$port) -or $port -lt 1024 -or $port -gt 65535) {
      throw "Native product config $key must be a port from 1024 to 65535."
    }
    $config[$key] = $port
  }
  $ports = @($config.postgresPort, $config.gatewayPort, $config.frontendPort)
  if (@($ports | Select-Object -Unique).Count -ne 3) {
    throw 'Native product ports must be distinct.'
  }
  if ([string]$config.jwtSecret -match '^(change-me|\s)' -or ([string]$config.jwtSecret).Length -lt 32) {
    throw 'Native product config requires an explicit JWT secret of at least 32 characters.'
  }
  if ([string]$config.adminPassword -match '[\r\n]' -or ([string]$config.adminPassword).Length -lt 12) {
    throw 'Native product config requires an explicit admin password of at least 12 characters.'
  }
  $uri = $null
  if (-not [uri]::TryCreate([string]$config.databaseUrl, [UriKind]::Absolute, [ref]$uri) -or
    $uri.Scheme -notin @('postgres', 'postgresql') -or $uri.Host -ne '127.0.0.1' -or
    $uri.Port -ne $config.postgresPort) {
    throw 'databaseUrl must use PostgreSQL on 127.0.0.1 and the configured postgresPort.'
  }
  if (-not $config.ContainsKey('nodePath') -or -not $config.nodePath) {
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $node) { throw 'node.exe was not found on PATH.' }
    $config.nodePath = $node.Source
  }
  if (-not [IO.Path]::IsPathFullyQualified([string]$config.nodePath) -or
    [string]$config.nodePath -match '["\r\n]') {
    throw 'nodePath must be an absolute Windows path.'
  }
  $config.nodePath = [IO.Path]::GetFullPath([string]$config.nodePath).TrimEnd('\')
  if (-not $config.ContainsKey('adminUsername') -or -not $config.adminUsername) { $config.adminUsername = 'admin' }
  if ([string]$config.adminUsername -match '[\r\n]') { throw 'adminUsername cannot contain newlines.' }
  $config.configPath = [IO.Path]::GetFullPath($ConfigPath)
  $config.statePath = Join-Path $config.runtimeRoot 'state\native-product.json'
  $config.logDir = Join-Path $config.runtimeRoot 'logs'

  if ($CheckFiles) {
    foreach ($item in @(
      @((Join-Path $config.pgBin 'pg_ctl.exe'), 'pg_ctl.exe'),
      @((Join-Path $config.pgBin 'postgres.exe'), 'postgres.exe'),
      @((Join-Path $config.pgBin 'pg_isready.exe'), 'pg_isready.exe'),
      @($config.pythonPath, 'product Python'),
      @($config.gatewayPythonPath, 'gateway Python'),
      @($config.nodePath, 'Node.js'),
      @((Join-Path $config.repoRoot 'scripts\run_uvicorn_win.py'), 'gateway launcher'),
      @((Join-Path $config.repoRoot 'frontend\node_modules\next\dist\bin\next'), 'Next.js CLI'),
      @((Join-Path $config.pgData 'PG_VERSION'), 'PostgreSQL data cluster')
    )) {
      if (-not (Test-Path -LiteralPath $item[0] -PathType Leaf)) { throw "Missing $($item[1]): $($item[0])" }
    }
    $runnerPath = Join-Path $config.repoRoot 'frontend\runner.config.json'
    if (-not (Test-Path -LiteralPath $runnerPath -PathType Leaf)) { throw "Missing runner config: $runnerPath" }
    try { $runner = Get-Content -LiteralPath $runnerPath -Raw | ConvertFrom-Json }
    catch { throw 'Frontend runner config is not valid JSON.' }
    $auto = @($runner.commands | Where-Object id -eq 'idpo_process_auto')
    if ($auto.Count -ne 1) { throw 'Frontend runner needs exactly one idpo_process_auto command.' }
    # Native mode sets IDPO_PRODUCT_PYTHON explicitly, allowing the parser runtime
    # to live on the configured data drive without changing tracked runner paths.
  }
  return $config
}

function Get-NativeProcessIdentity {
  param([Parameter(Mandatory)][int]$Id)
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $Id" -ErrorAction SilentlyContinue
  if (-not $process -or -not $process.ExecutablePath -or -not $process.CreationDate) { return $null }
  return [ordered]@{
    pid = [int]$process.ProcessId
    executable = [IO.Path]::GetFullPath([string]$process.ExecutablePath)
    startedUtc = $process.CreationDate.ToUniversalTime().ToString('o')
  }
}

function Test-NativeProcessIdentity {
  param($Expected)
  if (-not $Expected) { return $false }
  $actual = Get-NativeProcessIdentity -Id ([int]$Expected.pid)
  return [bool]($actual -and $actual.executable -ieq [string]$Expected.executable -and
    $actual.startedUtc -eq [string]$Expected.startedUtc)
}

function Get-NativeState {
  param($Config)
  if (-not (Test-Path -LiteralPath $Config.statePath -PathType Leaf)) { return $null }
  try { $state = Get-Content -LiteralPath $Config.statePath -Raw | ConvertFrom-Json -AsHashtable }
  catch { throw "Native process state is unreadable: $($Config.statePath)" }
  # PowerShell converts ISO JSON strings to DateTime in some versions. Restore
  # the canonical representation used by the receipt and CIM identity checks.
  if ($state.version -lt 2 -and $state.services['worker']) {
    throw 'Legacy process receipts cannot authorize a worker process.'
  }
  foreach ($name in @('postgres', 'gateway', 'frontend', 'worker')) {
    if ($state.services[$name] -and $state.services[$name].startedUtc -is [datetime]) {
      $state.services[$name].startedUtc = $state.services[$name].startedUtc.ToUniversalTime().ToString('o')
    }
  }
  if (-not (Test-NativeStateSignature -Config $Config -State $state)) {
    throw 'Native process state has changed or belongs to a different config. No process will be controlled.'
  }
  return $state
}

function Get-NativeStateSignature {
  param($Config, $State)
  $parts = [System.Collections.Generic.List[string]]::new()
  $parts.Add([string]$Config.configPath)
  $names = @('postgres', 'gateway', 'frontend')
  if ($State.version -ge 2) { $names += 'worker' }
  foreach ($name in $names) {
    $identity = if ($State.services) { $State.services[$name] } else { $null }
    $values = if ($identity) {
      @($name, $identity.pid, $identity.executable, $identity.startedUtc)
    } else { @($name, '', '', '') }
    foreach ($value in $values) {
      $parts.Add([string]$value)
    }
  }
  $payload = [Text.Encoding]::UTF8.GetBytes(($parts -join "`n"))
  $key = [Text.Encoding]::UTF8.GetBytes([string]$Config.jwtSecret)
  $hmac = [Security.Cryptography.HMACSHA256]::new($key)
  try { return [Convert]::ToHexString($hmac.ComputeHash($payload)) }
  finally { $hmac.Dispose() }
}

function Test-NativeStateSignature {
  param($Config, $State)
  if (-not $State -or -not $State.signature -or -not $State.services) { return $false }
  try {
    $expected = [Convert]::FromHexString((Get-NativeStateSignature -Config $Config -State $State))
    $actual = [Convert]::FromHexString([string]$State.signature)
    return [Security.Cryptography.CryptographicOperations]::FixedTimeEquals($expected, $actual)
  } catch { return $false }
}

function Save-NativeState {
  param($Config, $State)
  $State.signature = Get-NativeStateSignature -Config $Config -State $State
  $parent = Split-Path -Parent $Config.statePath
  New-Item -ItemType Directory -Path $parent -Force | Out-Null
  $temporary = "$($Config.statePath).tmp.$PID"
  try {
    $State | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $Config.statePath -Force
  } finally {
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
  }
}

function Get-NativePortOwners {
  param([int]$Port)
  return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
}

function Get-NativeDescendants {
  param($Root)
  if (-not (Test-NativeProcessIdentity $Root)) { return @() }
  $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
  $seen = @{}; $seen[[int]$Root.pid] = [datetime]::Parse([string]$Root.startedUtc).ToUniversalTime()
  $result = [System.Collections.Generic.List[object]]::new()
  $queue = [System.Collections.Generic.Queue[int]]::new()
  $queue.Enqueue([int]$Root.pid)
  while ($queue.Count) {
    $parentId = $queue.Dequeue()
    foreach ($child in $all) {
      $childId = [int]$child.ProcessId
      if ([int]$child.ParentProcessId -ne $parentId -or $seen.ContainsKey($childId) -or
        -not $child.CreationDate -or $child.CreationDate.ToUniversalTime() -lt $seen[$parentId]) { continue }
      $seen[$childId] = $child.CreationDate.ToUniversalTime()
      $queue.Enqueue($childId)
      $result.Add($childId)
    }
  }
  return @($result.ToArray())
}

function Test-NativePortOwnership {
  param([int]$Port, $Identity)
  $owners = @(Get-NativePortOwners $Port)
  if ($owners.Count -eq 0) { return $false }
  if (-not (Test-NativeProcessIdentity $Identity)) { return $false }
  $owned = @([int]$Identity.pid) + @(Get-NativeDescendants $Identity)
  foreach ($owner in $owners) { if ([int]$owner -notin $owned) { return $false } }
  return $true
}

function Assert-NativePortFree {
  param([int]$Port)
  if (@(Get-NativePortOwners $Port).Count -gt 0) {
    throw "Port $Port already has an untracked listener. Nothing was stopped."
  }
}

function Test-NativeWorkerHealth {
  param($Config, $Identity)
  if (-not (Test-NativeProcessIdentity $Identity)) { return $false }
  $healthPath = Join-Path $Config.dataDir 'frontend\execution-worker.json'
  try {
    $health = Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json
    $age = ((Get-Date).ToUniversalTime() - ([DateTime]$health.heartbeatAt).ToUniversalTime()).TotalSeconds
    return [int]$health.pid -eq [int]$Identity.pid -and $age -ge 0 -and $age -lt 90
  } catch { return $false }
}

function Get-NativeSummary {
  param($Config, $State)
  $services = [ordered]@{}
  foreach ($entry in @(@('postgres', $Config.postgresPort), @('gateway', $Config.gatewayPort),
    @('frontend', $Config.frontendPort))) {
    $name = $entry[0]; $port = [int]$entry[1]
    $identity = if ($State -and $State.services) { $State.services[$name] } else { $null }
    $services[$name] = [ordered]@{
      tracked = [bool]$identity
      processVerified = (Test-NativeProcessIdentity $identity)
      portOwned = (Test-NativePortOwnership -Port $port -Identity $identity)
      port = $port
    }
  }
  $workerIdentity = if ($State -and $State.services) { $State.services['worker'] } else { $null }
  $services.worker = [ordered]@{ tracked = [bool]$workerIdentity
    processVerified = (Test-NativeProcessIdentity $workerIdentity)
    healthy = (Test-NativeWorkerHealth -Config $Config -Identity $workerIdentity) }
  return $services
}

function Quote-NativeArgument {
  param([string]$Value)
  if ($Value -match '["\r\n]') { throw 'An executable argument contains unsupported characters.' }
  return '"' + $Value + '"'
}

function Start-NativeChild {
  param([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory,
    [string]$LogDirectory, [string]$Name, [hashtable]$Environment = @{})
  New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
  $saved = @{}
  foreach ($key in $Environment.Keys) {
    $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], 'Process')
  }
  try {
    $quoted = ($Arguments | ForEach-Object { Quote-NativeArgument $_ }) -join ' '
    $proc = Start-Process -FilePath $Executable -ArgumentList $quoted -WorkingDirectory $WorkingDirectory `
      -RedirectStandardOutput (Join-Path $LogDirectory "$Name.out.log") `
      -RedirectStandardError (Join-Path $LogDirectory "$Name.err.log") `
      -WindowStyle Hidden -PassThru
    return $proc
  } finally {
    foreach ($key in $Environment.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
  }
}

function Wait-NativeHttpHealth {
  param([int]$Port, [string]$Path, [string]$ExpectedStatus, $Identity, [int]$Seconds = 45)
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    if (-not (Test-NativeProcessIdentity $Identity)) { return $false }
    try {
      $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port$Path" -TimeoutSec 2 -UseBasicParsing
      $body = $response.Content | ConvertFrom-Json
      if ($response.StatusCode -eq 200 -and $body.status -eq $ExpectedStatus -and
        (Test-NativePortOwnership -Port $Port -Identity $Identity)) { return $true }
    } catch { }
    Start-Sleep -Milliseconds 600
  } while ((Get-Date) -lt $deadline)
  return $false
}

function Stop-NativeOwnedTree {
  param($Identity)
  if (-not $Identity -or -not (Test-NativeProcessIdentity $Identity)) { return $false }
  $descendants = @(Get-NativeDescendants $Identity | ForEach-Object { Get-NativeProcessIdentity -Id ([int]$_) } |
    Where-Object { $_ })
  [array]::Reverse($descendants)
  foreach ($child in $descendants) {
    if (Test-NativeProcessIdentity $child) { Stop-Process -Id ([int]$child.pid) -Force -ErrorAction SilentlyContinue }
  }
  if (Test-NativeProcessIdentity $Identity) {
    Stop-Process -Id ([int]$Identity.pid) -Force -ErrorAction SilentlyContinue
  }
  return $true
}
