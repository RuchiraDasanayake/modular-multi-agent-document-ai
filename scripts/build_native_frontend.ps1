#requires -Version 7.2
param([Parameter(Mandatory)][string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native_product_common.ps1')
Assert-NativeWindows
$config = Get-NativeConfig -ConfigPath $ConfigPath -CheckFiles
$paths = Get-NativeFrontendBuildPaths -Config $config
$state = Get-NativeState -Config $config
if ($state -and $state.services.ContainsKey('frontend') -and
    (Test-NativeProcessIdentity $state.services.frontend) -and $config.frontendMode -eq 'production') {
  throw 'Stop the tracked production stack before replacing its frontend build.'
}
New-Item -ItemType Directory -Path $paths.target, (Split-Path -Parent $paths.receipt) -Force | Out-Null
if (Test-Path -LiteralPath $paths.cache) {
  $cache = Get-Item -LiteralPath $paths.cache
  if ($cache.LinkType -ne 'Junction' -or
      [IO.Path]::GetFullPath([string]$cache.Target).TrimEnd('\') -ine [IO.Path]::GetFullPath($paths.target).TrimEnd('\')) {
    throw 'Native build cache already exists at another location. Inspect it before changing storage.'
  }
} else {
  New-Item -ItemType Junction -Path $paths.cache -Target $paths.target | Out-Null
}
# Node resolves external packages from the physical build location on the data
# drive. Keep a checked sibling dependency junction outside Next's cleaned output.
if (Test-Path -LiteralPath $paths.dependencies) {
  $dependencies = Get-Item -LiteralPath $paths.dependencies
  if ($dependencies.LinkType -ne 'Junction' -or
      [IO.Path]::GetFullPath([string]$dependencies.Target).TrimEnd('\') -ine
        [IO.Path]::GetFullPath($paths.dependencyTarget).TrimEnd('\')) {
    throw 'Native build dependencies already exist at another location.'
  }
} else {
  New-Item -ItemType Junction -Path $paths.dependencies -Target $paths.dependencyTarget | Out-Null
}
$fingerprint = Get-NativeFrontendFingerprint -Config $config
# Remove only the build receipt; a failed build must never reuse stale readiness.
Remove-Item -LiteralPath $paths.receipt -Force -ErrorAction SilentlyContinue
$environment = @{
  NODE_ENV = 'production'; IDPO_NATIVE_FRONTEND = '1'; NEXT_TELEMETRY_DISABLED = '1'
  IDPO_DATA_DIR = [string]$config.dataDir
  INTERNAL_API_URL = "http://127.0.0.1:$($config.gatewayPort)"
  NEXT_PUBLIC_API_URL = "http://127.0.0.1:$($config.gatewayPort)"
}
$nextCli = Join-Path $config.repoRoot 'frontend\node_modules\next\dist\bin\next'
$process = Start-NativeChild -Executable $config.nodePath -Arguments @($nextCli, 'build', '--webpack') `
  -WorkingDirectory (Join-Path $config.repoRoot 'frontend') -LogDirectory $config.logDir `
  -Name 'frontend-build' -Environment $environment
$identity = Get-NativeProcessIdentity -Id $process.Id
try {
  $deadline = (Get-Date).AddMinutes(15)
  do {
    if ($process.WaitForExit(1000)) { break }
  } while ((Get-Date) -lt $deadline)
  if (-not $process.HasExited) {
    if ($identity) { [void](Stop-NativeOwnedTree -Identity $identity) }
    throw 'Frontend build exceeded 15 minutes. Inspect the frontend-build logs.'
  }
  $process.WaitForExit()
  if ($process.ExitCode -ne 0) { throw 'Frontend build failed. Inspect frontend-build.out.log and frontend-build.err.log.' }
  if ((Get-NativeFrontendFingerprint -Config $config) -ne $fingerprint) {
    throw 'Frontend source changed during the build. Build again after edits are complete.'
  }
  $buildId = (Get-Content -LiteralPath (Join-Path $paths.cache 'BUILD_ID') -Raw).Trim()
  if (-not $buildId) { throw 'Frontend build produced no build identity.' }
  $receipt = @{ version = 1; mode = 'production'; buildId = $buildId; sourceSha256 = $fingerprint;
    gatewayPort = $config.gatewayPort; completedUtc = [DateTime]::UtcNow.ToString('o') }
  $temporary = $paths.receipt + '.tmp'
  $receipt | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding utf8
  Move-Item -LiteralPath $temporary -Destination $paths.receipt -Force
  Assert-NativeFrontendBuild -Config $config
  Write-Output "Native frontend production build verified. Receipt: $($paths.receipt)"
} finally {
  $process.Dispose()
}
