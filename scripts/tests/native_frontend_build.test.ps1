#requires -Version 7.2
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'native_product_common.ps1')
function Assert-BuildTest { param([bool]$Condition, [string]$Message)
  if (-not $Condition) { throw "FAIL: $Message" }
}
function Assert-BuildThrows { param([scriptblock]$Action)
  $failed = $false
  try { & $Action } catch { $failed = $true }
  Assert-BuildTest $failed 'Invalid build must be rejected.'
}
$testRoot = Join-Path $env:TEMP ('docai-build-test-' + [guid]::NewGuid().ToString('N'))
try {
  $config = @{ repoRoot = $testRoot; runtimeRoot = (Join-Path $testRoot 'runtime'); gatewayPort = 8123;
    configPath = (Join-Path $testRoot 'config.json'); jwtSecret = 'test-secret-not-used-by-any-service';
    statePath = (Join-Path $testRoot 'runtime\state\native-product.json') }
  $paths = Get-NativeFrontendBuildPaths $config
  New-Item -ItemType Directory -Path (Join-Path $testRoot 'frontend\src'), $paths.target,
    $paths.dependencyTarget, (Split-Path -Parent $paths.receipt) -Force | Out-Null
  $source = Join-Path $testRoot 'frontend\src\page.tsx'
  'source one' | Set-Content -LiteralPath $source
  New-Item -ItemType Junction -Path $paths.cache -Target $paths.target | Out-Null
  New-Item -ItemType Junction -Path $paths.dependencies -Target $paths.dependencyTarget | Out-Null
  'build-one' | Set-Content -LiteralPath (Join-Path $paths.target 'BUILD_ID')
  Assert-BuildThrows { Assert-NativeFrontendBuild $config }
  $receipt = @{ version = 1; mode = 'production'; buildId = 'build-one'; gatewayPort = 8123;
    sourceSha256 = (Get-NativeFrontendFingerprint $config) }
  $receipt | ConvertTo-Json | Set-Content -LiteralPath $paths.receipt
  Assert-NativeFrontendBuild $config
  'source two' | Set-Content -LiteralPath $source
  Assert-BuildThrows { Assert-NativeFrontendBuild $config }
  'source one' | Set-Content -LiteralPath $source
  $config.gatewayPort = 8124
  Assert-BuildThrows { Assert-NativeFrontendBuild $config }
  $config.gatewayPort = 8123
  'build-two' | Set-Content -LiteralPath (Join-Path $paths.target 'BUILD_ID')
  Assert-BuildThrows { Assert-NativeFrontendBuild $config }
  $identity = Get-NativeProcessIdentity -Id $PID
  $state = @{ version = 3; frontendMode = 'production'; services = @{frontend = $identity}; signature = '' }
  Save-NativeState $config $state
  Assert-BuildTest ((Get-NativeState $config).frontendMode -eq 'production') 'Frontend mode round trip.'
  $state.frontendMode = 'development'
  $state | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $config.statePath
  Assert-BuildThrows { Get-NativeState $config }
  Write-Output 'native_frontend_build.test.ps1: PASS'
} finally {
  $resolved = [IO.Path]::GetFullPath($testRoot)
  $tempPrefix = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
  if (-not $resolved.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase) -or
      -not ([IO.Path]::GetFileName($resolved)).StartsWith('docai-build-test-')) { throw 'Unsafe cleanup path.' }
  # Remove the test junction itself before deleting the explicitly bounded fixture.
  if (Test-Path -LiteralPath $paths.cache) { Remove-Item -LiteralPath $paths.cache -Force }
  if (Test-Path -LiteralPath $paths.dependencies) { Remove-Item -LiteralPath $paths.dependencies -Force }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}
