#requires -Version 7.2
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'native_product_common.ps1')

function Assert-PreflightTest {
  param([bool]$Condition, [string]$Message)
  if (-not $Condition) { throw "FAIL: $Message" }
}

function Expect-PreflightFailure {
  param([scriptblock]$Action, [string]$Expected)
  $message = $null
  try { & $Action | Out-Null } catch { $message = $_.Exception.Message }
  Assert-PreflightTest ($message -and $message.Contains($Expected)) "Expected failure: $Expected"
  Assert-PreflightTest (-not $message.Contains('DO_NOT_RETAIN_SECRET')) 'Failure text excludes raw probe output.'
}

Assert-NativeWindows
$testRoot = Join-Path $env:TEMP ('docai-preflight-test-' + [guid]::NewGuid().ToString('N'))
$node = (Get-Command node.exe -ErrorAction Stop).Source
New-Item -ItemType Directory -Path (Join-Path $testRoot 'scripts') | Out-Null
$configPath = Join-Path $testRoot 'config.json'
$stateDir = Join-Path $testRoot 'state'
$reportPath = Join-Path $stateDir 'product-capabilities.json'
$config = @{ repoRoot = $testRoot; runtimeRoot = $testRoot; configPath = $configPath
  statePath = (Join-Path $stateDir 'native-product.json'); pythonPath = $node }
$stub = @'
const fs = require('node:fs');
const path = require('node:path');
const args = process.argv.slice(2);
const config = JSON.parse(fs.readFileSync(args[args.indexOf('--native-config') + 1], 'utf8').replace(/^\uFEFF/, ''));
fs.writeFileSync(path.join(config.repoRoot, 'probe-receipt.json'), JSON.stringify({ pid: process.pid, args }));
process.stderr.write('DO_NOT_RETAIN_SECRET in raw dependency output\n');
if (config.fixtureMode === 'hang') {
  setInterval(() => {}, 1000);
} else if (config.fixtureMode === 'invalid-json') {
  process.stdout.write('{DO_NOT_RETAIN_SECRET');
} else {
  process.stdout.write(JSON.stringify(config.fixtureReport));
  process.exitCode = config.fixtureExitCode || 0;
}
'@
# Node executes this deterministic stub instead of Python. No product packages,
# provider requests, database or running native services are involved.
$stub | Set-Content -LiteralPath (Join-Path $testRoot 'scripts\check_product_runtime.py') -Encoding utf8

function New-ReadyPayload {
  $checks = @('core', 'text_json', 'pdf_native', 'image_codecs', 'pdfium', 'pdf_rasterizer',
    'tesseract_ocr', 'scan_sample', 'docx', 'xlsx', 'pptx', 'html', 'eml', 'model_client') | ForEach-Object {
      @{ id = $_; ready = $true; remedy = 'DO_NOT_RETAIN_SECRET' }
    }
  $capabilities = @{}
  foreach ($name in @('text_json', 'pdf_native_text', 'image_ocr', 'pdf_scan_extraction',
    'pdf_scan_schema_sampling', 'docx', 'xlsx', 'pptx', 'html', 'eml')) {
    $capabilities[$name] = @{ ready = $true; missing_checks = @() }
  }
  return @{ contract_version = 1; status = 'ready'; checks = @($checks); capabilities = $capabilities
    network_calls_made = $false; unexpected = 'DO_NOT_RETAIN_SECRET'
    provider = @{ mode = 'cloud'; state = 'configured_unverified'; client_ready = $true
      configuration_valid = $true; network_checked = $false; key = 'DO_NOT_RETAIN_SECRET' } }
}

function Save-ProbeConfig {
  param([string]$Mode = 'report', [int]$ExitCode = 0, $Payload = (New-ReadyPayload))
  $script:config.fixtureMode = $Mode
  $script:config.fixtureReport = $Payload
  $script:config.fixtureExitCode = $ExitCode
  $script:config | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $configPath -Encoding utf8
}

try {
  Save-ProbeConfig
  $ready = Invoke-NativeProductPreflight -Config $config
  Assert-PreflightTest ($ready.status -eq 'ready') 'Complete offline capability report passes.'
  $stored = Get-Content -LiteralPath $reportPath -Raw
  Assert-PreflightTest (-not $stored.Contains('DO_NOT_RETAIN_SECRET')) 'Receipt excludes unknown fields and raw diagnostics.'
  $receipt = Get-Content -LiteralPath (Join-Path $testRoot 'probe-receipt.json') -Raw | ConvertFrom-Json
  Assert-PreflightTest (($receipt.args -join '|') -eq "--native-config|$configPath|--json") 'Probe receives only its private config path and JSON flag.'

  $config.autoOcrEngine = 'rapidocr'; $config.rapidOcrTimeoutSeconds = 120
  Save-ProbeConfig
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config } 'invalid_report'
  $rapidPayload = New-ReadyPayload
  $rapidPayload.optional_ocr = @{ engine = 'rapidocr'; id = 'rapidocr_ocr'; ready = $true; raw = 'DO_NOT_RETAIN_SECRET' }
  Save-ProbeConfig -Payload $rapidPayload
  Assert-PreflightTest ((Invoke-NativeProductPreflight -Config $config).status -eq 'ready') 'Explicit RapidOCR requires its successful check.'
  $receipt = Get-Content -LiteralPath (Join-Path $testRoot 'probe-receipt.json') -Raw | ConvertFrom-Json
  Assert-PreflightTest (($receipt.args -join '|').EndsWith('|--ocr-engine|rapidocr')) 'Selected optional OCR reaches the probe.'
  $rapidPayload.optional_ocr.ready = $false
  Save-ProbeConfig -Payload $rapidPayload
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config } 'capability_unavailable'
  $stored = Get-Content -LiteralPath $reportPath -Raw
  Assert-PreflightTest (-not $stored.Contains('DO_NOT_RETAIN_SECRET')) 'Optional OCR report excludes raw diagnostics.'
  $config.Remove('autoOcrEngine'); $config.Remove('rapidOcrTimeoutSeconds')

  $missing = New-ReadyPayload
  $missing.capabilities.pdf_native_text.ready = $false
  # A lying overall status or zero process exit cannot hide a failed capability.
  Save-ProbeConfig -Payload $missing
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config } 'capability_unavailable'
  $stored = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
  Assert-PreflightTest ($stored.status -eq 'unavailable' -and 'pdf_native_text' -in $stored.failed_capabilities) 'Failure replaces a previously ready receipt.'

  # Normal Python capability failures omit the optional top-level code. Strict
  # PowerShell mode must not turn this valid report into an invalid-report error.
  $unavailable = New-ReadyPayload
  $unavailable.status = 'unavailable'
  ($unavailable.checks | Where-Object id -eq 'scan_sample').ready = $false
  $unavailable.capabilities.pdf_scan_schema_sampling.ready = $false
  Save-ProbeConfig -Payload $unavailable -ExitCode 1
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config } 'probe_process_failed'
  $stored = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
  Assert-PreflightTest ('scan_sample' -in $stored.failed_checks -and
    'pdf_scan_schema_sampling' -in $stored.failed_capabilities) 'Valid unavailable report retains the actual failed capability.'
  Save-ProbeConfig -Payload $unavailable
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config } 'capability_unavailable'

  $missingCheck = New-ReadyPayload
  $missingCheck.checks = @($missingCheck.checks | Where-Object id -ne 'core')
  Save-ProbeConfig -Payload $missingCheck
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config } 'invalid_report'

  $badProvider = New-ReadyPayload
  $badProvider.provider.client_ready = $false
  Save-ProbeConfig -Payload $badProvider
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config } 'capability_unavailable'

  $localOnly = New-ReadyPayload
  ($localOnly.checks | Where-Object id -eq 'model_client').ready = $false
  $localOnly.provider = @{ mode = 'disabled'; state = 'not_configured'; client_ready = $false
    configuration_valid = $true; network_checked = $false }
  Save-ProbeConfig -Payload $localOnly
  Assert-PreflightTest ((Invoke-NativeProductPreflight -Config $config).status -eq 'ready') 'No-model parsing does not require a provider client.'

  Save-ProbeConfig -ExitCode 1
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config } 'probe_process_failed'
  Save-ProbeConfig -Mode 'invalid-json'
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config } 'invalid_report'
  Assert-PreflightTest (-not (Get-Content -LiteralPath $reportPath -Raw).Contains('DO_NOT_RETAIN_SECRET')) 'Invalid JSON is never retained in the report.'

  Save-ProbeConfig -Mode 'hang'
  Expect-PreflightFailure { Invoke-NativeProductPreflight -Config $config -TimeoutSeconds 1 } 'probe_timeout'
  $hung = Get-Content -LiteralPath (Join-Path $testRoot 'probe-receipt.json') -Raw | ConvertFrom-Json
  Assert-PreflightTest (-not (Get-NativeProcessIdentity -Id $hung.pid)) 'Timed-out probe process is stopped.'
  Assert-PreflightTest (@(Get-ChildItem -LiteralPath $stateDir -Filter '*.tmp' -Force).Count -eq 0) 'Temporary stdout/stderr captures are removed.'

  # Exercise startup itself: a failed preflight must be reached before any
  # PostgreSQL/application process launch, even with all required files present.
  $config.pgBin = Join-Path $testRoot 'pgbin'
  $config.pgData = Join-Path $testRoot 'pgdata'
  $config.postgresPort = 55031; $config.gatewayPort = 55032; $config.frontendPort = 55033
  $config.databaseUrl = 'postgresql://user:pass@127.0.0.1:55031/docai'
  $config.jwtSecret = 'fixture-secret-1234567890123456789012345'
  $config.adminPassword = 'long-test-password'
  $config.dataDir = Join-Path $testRoot 'data'
  $config.gatewayPythonPath = $node; $config.nodePath = $node
  foreach ($file in @('pgbin\pg_ctl.exe', 'pgbin\postgres.exe', 'pgbin\pg_isready.exe', 'pgdata\PG_VERSION',
      'scripts\run_uvicorn_win.py', 'frontend\node_modules\next\dist\bin\next')) {
    $target = Join-Path $testRoot $file
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    New-Item -ItemType File -Path $target | Out-Null
  }
  @{ commands = @(@{ id = 'idpo_process_auto'; program = $node }) } | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $testRoot 'frontend\runner.config.json')
  Save-ProbeConfig -Payload $missing
  $startScript = Join-Path (Split-Path -Parent $PSScriptRoot) 'start_native_product.ps1'
  Expect-PreflightFailure { & $startScript -ConfigPath $configPath } 'Product runtime preflight failed'
  Assert-PreflightTest (-not (Test-Path -LiteralPath $config.statePath)) 'Failed preflight creates no service receipt.'
  Assert-PreflightTest (-not (Test-Path -LiteralPath (Join-Path $testRoot 'logs\pgctl-start.out.log'))) 'Failed preflight never starts PostgreSQL.'
  Write-Output 'native_product_preflight.test.ps1: PASS'
} finally {
  # Retain cleanup even if a regression leaves the timeout fixture alive. Only
  # this test process's own Node child may be stopped from its fixture receipt.
  $probeReceipt = Join-Path $testRoot 'probe-receipt.json'
  if (Test-Path -LiteralPath $probeReceipt) {
    try {
      $record = Get-Content -LiteralPath $probeReceipt -Raw | ConvertFrom-Json
      $child = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$record.pid)" -ErrorAction SilentlyContinue
      if ($child -and [int]$child.ParentProcessId -eq $PID -and [string]$child.ExecutablePath -ieq $node) {
        $owned = Get-NativeProcessIdentity -Id ([int]$record.pid)
        if ($owned) { [void](Stop-NativeOwnedTree -Identity $owned) }
      }
    } catch { }
  }
  $resolvedRoot = [IO.Path]::GetFullPath($testRoot)
  $tempPrefix = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
  if (-not $resolvedRoot.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase) -or
      -not ([IO.Path]::GetFileName($resolvedRoot)).StartsWith('docai-preflight-test-')) {
    throw 'Unsafe preflight test cleanup path.'
  }
  Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
}
