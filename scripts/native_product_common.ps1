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
  foreach ($limit in @(@('autoMaxOutputTokens', 16384), @('autoTimeoutSeconds', 600))) {
    $key = [string]$limit[0]
    if ($config.ContainsKey($key) -and $null -ne $config[$key]) {
      $value = 0
      if (-not [int]::TryParse([string]$config[$key], [ref]$value) -or $value -lt 1 -or $value -gt [int]$limit[1]) {
        throw "Native product config $key must be an integer from 1 to $($limit[1])."
      }
      $config[$key] = $value
    }
  }
  if (-not $config.ContainsKey('autoOcrEngine')) { $config.autoOcrEngine = 'tesseract' }
  if ($config.autoOcrEngine -notin @('tesseract', 'rapidocr')) { throw 'autoOcrEngine must be tesseract or rapidocr.' }
  if (-not $config.ContainsKey('autoResponseFormat')) { $config.autoResponseFormat = 'plain_json' }
  if ($config.autoResponseFormat -notin @('plain_json', 'strict_confirmed_values_v1')) {
    throw 'autoResponseFormat must be plain_json or strict_confirmed_values_v1.'
  }
  if (-not $config.ContainsKey('autoLongDocument')) { $config.autoLongDocument = 'reject' }
  if ($config.autoLongDocument -notin @('reject', 'bounded_text_segments_v1')) {
    throw 'autoLongDocument must be reject or bounded_text_segments_v1.'
  }
  if (-not $config.ContainsKey('autoVisualDocument')) { $config.autoVisualDocument = 'disabled' }
  if ($config.autoVisualDocument -notin @('disabled', 'bounded_visual_v1')) {
    throw 'autoVisualDocument must be disabled or bounded_visual_v1.'
  }
  if ($config.autoOcrEngine -eq 'rapidocr') {
    foreach ($key in @('rapidOcrPythonPath', 'rapidOcrWorkDir')) {
      if (-not $config.ContainsKey($key) -or -not [IO.Path]::IsPathFullyQualified([string]$config[$key]) -or
          [string]$config[$key] -match '["\r\n]') { throw "$key must be an absolute Windows path." }
      $config[$key] = [IO.Path]::GetFullPath([string]$config[$key]).TrimEnd('\')
    }
    foreach ($limit in @(@('rapidOcrTimeoutSeconds', 120, 1, 180), @('rapidOcrMaxRssMiB', 1536, 128, 2048))) {
      $key = [string]$limit[0]
      if (-not $config.ContainsKey($key)) { $config[$key] = $limit[1] }
      $number = 0
      if (-not [int]::TryParse([string]$config[$key], [ref]$number) -or $number -lt $limit[2] -or $number -gt $limit[3]) {
        throw "$key is outside its supported integer limits."
      }
      $config[$key] = $number
    }
    if ($CheckFiles -and (-not (Test-Path -LiteralPath $config.rapidOcrPythonPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $config.rapidOcrWorkDir -PathType Container))) {
      throw 'The configured RapidOCR interpreter or scratch directory is unavailable.'
    }
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
  if (-not $config.ContainsKey('frontendMode')) { $config.frontendMode = 'development' }
  if ($config.frontendMode -notin @('development', 'production')) {
    throw 'frontendMode must be development or production.'
  }
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
      @((Join-Path $config.repoRoot 'scripts\check_product_runtime.py'), 'product runtime preflight'),
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

function Get-NativeFrontendFingerprint {
  param($Config)
  $root = Join-Path $Config.repoRoot 'frontend'
  $files = [Collections.Generic.List[string]]::new()
  foreach ($directory in @('src', 'public', 'scripts')) {
    $folder = Join-Path $root $directory
    if (Test-Path -LiteralPath $folder -PathType Container) {
      foreach ($file in Get-ChildItem -LiteralPath $folder -File -Recurse) { $files.Add($file.FullName) }
    }
  }
  foreach ($name in @('package.json', 'package-lock.json', 'next.config.js', 'tsconfig.json',
      'tailwind.config.ts', 'tailwind.config.js', 'postcss.config.js', 'runner.config.json')) {
    $file = Join-Path $root $name
    if (Test-Path -LiteralPath $file -PathType Leaf) { $files.Add($file) }
  }
  $manifest = foreach ($file in ($files | Sort-Object -Unique)) {
    $relative = [IO.Path]::GetRelativePath($root, $file).Replace('\', '/')
    "$relative=$((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant())"
  }
  $bytes = [Text.Encoding]::UTF8.GetBytes(($manifest -join "`n"))
  return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
}

function Get-NativeFrontendBuildPaths {
  param($Config)
  return @{
    cache = Join-Path $Config.repoRoot 'frontend\.next-product'
    target = Join-Path $Config.runtimeRoot 'frontend-build\output'
    dependencies = Join-Path $Config.runtimeRoot 'frontend-build\node_modules'
    dependencyTarget = Join-Path $Config.repoRoot 'frontend\node_modules'
    receipt = Join-Path $Config.runtimeRoot 'state\frontend-build.json'
  }
}

function Assert-NativeFrontendBuild {
  param($Config)
  $paths = Get-NativeFrontendBuildPaths -Config $Config
  try {
    $receipt = Get-Content -LiteralPath $paths.receipt -Raw | ConvertFrom-Json -AsHashtable
    $buildId = (Get-Content -LiteralPath (Join-Path $paths.cache 'BUILD_ID') -Raw).Trim()
    $cache = Get-Item -LiteralPath $paths.cache
    $target = [IO.Path]::GetFullPath([string]$cache.Target).TrimEnd('\')
    $dependencies = Get-Item -LiteralPath $paths.dependencies
    $valid = $receipt.version -eq 1 -and $receipt.mode -eq 'production' -and
      $receipt.buildId -eq $buildId -and $buildId.Length -gt 0 -and
      $receipt.gatewayPort -eq $Config.gatewayPort -and
      $receipt.sourceSha256 -eq (Get-NativeFrontendFingerprint -Config $Config) -and
      $cache.LinkType -eq 'Junction' -and $target -ieq [IO.Path]::GetFullPath($paths.target).TrimEnd('\') -and
      $dependencies.LinkType -eq 'Junction' -and
      [IO.Path]::GetFullPath([string]$dependencies.Target).TrimEnd('\') -ieq
        [IO.Path]::GetFullPath($paths.dependencyTarget).TrimEnd('\')
    if ($valid) { return }
  } catch { }
  throw 'Native frontend build is missing, stale or configured for another gateway. Run scripts/build_native_frontend.ps1 with this config before production startup.'
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
  if ($state.version -notin @(1, 2, 3) -or
      ($state.version -eq 3 -and $state.frontendMode -notin @('development', 'production'))) {
    throw 'Native process receipt version or frontend mode is invalid.'
  }
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
  if ($State.version -eq 3) { $parts.Add('version3'); $parts.Add([string]$State.frontendMode) }
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

function ConvertTo-NativeCapabilityReport {
  param($Payload, [int]$ExitCode, [ValidateSet('tesseract', 'rapidocr')][string]$OcrEngine = 'tesseract')
  # Retain only known fields and enum values. Raw child output may contain
  # third-party diagnostics and must never be saved as the capability receipt.
  $safe = [ordered]@{ contract_version = 1; checkedAt = (Get-Date).ToUniversalTime().ToString('o')
    status = 'unavailable'; code = 'invalid_report'; failed_checks = @(); failed_capabilities = @() }
  if ($Payload -isnot [System.Collections.IDictionary] -or $Payload.contract_version -ne 1) { return $safe }
  if ($Payload.status -eq 'unavailable' -and $Payload.code -in @('invalid_native_config',
      'wrong_python_runtime', 'runtime_preflight_failed')) {
    $safe.code = $Payload.code
    return $safe
  }
  if ($Payload.status -notin @('ready', 'unavailable') -or $Payload.network_calls_made -isnot [bool] -or
    $Payload.network_calls_made -or $Payload.checks -isnot [array] -or
    $Payload.capabilities -isnot [System.Collections.IDictionary] -or
    $Payload.provider -isnot [System.Collections.IDictionary]) { return $safe }
  $checkNames = @('core', 'text_json', 'pdf_native', 'image_codecs', 'pdfium', 'pdf_rasterizer',
    'tesseract_ocr', 'scan_sample', 'docx', 'xlsx', 'pptx', 'html', 'eml', 'model_client')
  $checked = @{}
  foreach ($check in $Payload.checks) {
    if ($check -isnot [System.Collections.IDictionary] -or $check.id -notin $checkNames -or
      $check.ready -isnot [bool] -or $checked.ContainsKey([string]$check.id)) { return $safe }
    $checked[[string]$check.id] = [bool]$check.ready
  }
  if ($checked.Count -ne $checkNames.Count) { return $safe }
  $optionalReady = $true
  if ($OcrEngine -eq 'rapidocr') {
    $optional = $Payload.optional_ocr
    if ($optional -isnot [System.Collections.IDictionary] -or $optional.engine -ne 'rapidocr' -or
        $optional.id -ne 'rapidocr_ocr' -or $optional.ready -isnot [bool]) { return $safe }
    $optionalReady = $optional.ready
    $safe.optional_ocr = [ordered]@{ engine = 'rapidocr'; ready = [bool]$optionalReady }
  }
  $capabilityNames = @('text_json', 'pdf_native_text', 'image_ocr', 'pdf_scan_extraction',
    'pdf_scan_schema_sampling', 'docx', 'xlsx', 'pptx', 'html', 'eml')
  $capabilities = [ordered]@{}
  foreach ($name in $capabilityNames) {
    $item = $Payload.capabilities[$name]
    if ($item -isnot [System.Collections.IDictionary] -or $item.ready -isnot [bool]) { return $safe }
    $capabilities[$name] = [bool]$item.ready
  }
  $provider = $Payload.provider
  if ($provider.mode -notin @('disabled', 'invalid', 'local', 'cloud') -or
    $provider.state -notin @('not_configured', 'configured_unverified', 'unavailable') -or
    $provider.configuration_valid -isnot [bool] -or $provider.client_ready -isnot [bool] -or
    $provider.network_checked -isnot [bool] -or $provider.network_checked) { return $safe }
  $providerReady = $provider.configuration_valid -and (
    ($provider.mode -eq 'disabled' -and $provider.state -eq 'not_configured') -or
    ($provider.mode -in @('local', 'cloud') -and $provider.state -eq 'configured_unverified' -and
      $provider.client_ready -and $checked.model_client))
  $safe.failed_checks = @($checkNames | Where-Object { -not $checked[$_] })
  if (-not $optionalReady) { $safe.failed_checks += 'rapidocr_ocr' }
  $safe.failed_capabilities = @($capabilityNames | Where-Object { -not $capabilities[$_] })
  $safe.capabilities = $capabilities
  $safe.provider = [ordered]@{ mode = [string]$provider.mode; state = [string]$provider.state
    client_ready = [bool]$provider.client_ready; network_checked = $false }
  $requiredFailed = @($safe.failed_checks | Where-Object { $_ -ne 'model_client' })
  $safe.code = 'capability_unavailable'
  if ($ExitCode -ne 0) { $safe.code = 'probe_process_failed' }
  elseif ($Payload.status -eq 'ready' -and $safe.failed_capabilities.Count -eq 0 -and
    $requiredFailed.Count -eq 0 -and $providerReady) {
    $safe.status = 'ready'
    $safe.code = 'synthetic_capabilities_verified'
  }
  return $safe
}

function Invoke-NativeProductPreflight {
  param($Config, [ValidateRange(1, 240)][int]$TimeoutSeconds = 60)
  $ErrorActionPreference = 'Stop'
  $directory = Split-Path -Parent $Config.statePath
  New-Item -ItemType Directory -Path $directory -Force | Out-Null
  $reportPath = Join-Path $directory 'product-capabilities.json'
  $stem = Join-Path $directory ('.product-preflight-' + [guid]::NewGuid().ToString('N'))
  $stdoutPath = "$stem.out.tmp"
  $stderrPath = "$stem.err.tmp"
  $reportTemporary = "$stem.report.tmp"
  $process = $null
  $identity = $null
  $report = [ordered]@{ contract_version = 1; checkedAt = (Get-Date).ToUniversalTime().ToString('o')
    status = 'unavailable'; code = 'probe_start_failed'; failed_checks = @(); failed_capabilities = @() }
  try {
    try {
      $engine = if ($Config.ContainsKey('autoOcrEngine')) { [string]$Config.autoOcrEngine } else { 'tesseract' }
      if (-not $PSBoundParameters.ContainsKey('TimeoutSeconds') -and $engine -eq 'rapidocr') {
        $TimeoutSeconds = [Math]::Max(60, [int]$Config.rapidOcrTimeoutSeconds + 30)
      }
      $arguments = @((Join-Path $Config.repoRoot 'scripts\check_product_runtime.py'),
        '--native-config', [string]$Config.configPath, '--json')
      if ($engine -eq 'rapidocr') { $arguments += @('--ocr-engine', 'rapidocr') }
      $quoted = ($arguments | ForEach-Object { Quote-NativeArgument $_ }) -join ' '
      $process = Start-Process -FilePath $Config.pythonPath -ArgumentList $quoted `
        -WorkingDirectory $Config.repoRoot -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
      $identity = Get-NativeProcessIdentity -Id $process.Id
      if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $report.code = 'probe_timeout'
        if ($identity) { [void](Stop-NativeOwnedTree -Identity $identity) }
        if (-not $process.WaitForExit(5000)) { $report.code = 'probe_timeout_cleanup_failed' }
      } else {
        # WaitForExit flushes redirected streams before their files are inspected.
        $process.WaitForExit()
        $report.code = 'invalid_report'
        if ((Get-Item -LiteralPath $stdoutPath).Length -le 65536) {
          $payload = Get-Content -LiteralPath $stdoutPath -Raw | ConvertFrom-Json -AsHashtable
          $report = ConvertTo-NativeCapabilityReport -Payload $payload -ExitCode $process.ExitCode -OcrEngine $engine
        }
      }
    } catch {
      # Keep the bounded error code; never print process output or exception text.
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportTemporary -Encoding utf8
    Move-Item -LiteralPath $reportTemporary -Destination $reportPath -Force
    if ($report.status -ne 'ready') {
      $failed = if ($report.failed_capabilities.Count) { ' Unavailable: ' + ($report.failed_capabilities -join ', ') + '.' } else { '' }
      throw "Product runtime preflight failed ($($report.code)).$failed Report: $reportPath"
    }
    return $report
  } finally {
    if ($process) { $process.Dispose() }
    foreach ($temporary in @($stdoutPath, $stderrPath, $reportTemporary)) {
      Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
  }
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
