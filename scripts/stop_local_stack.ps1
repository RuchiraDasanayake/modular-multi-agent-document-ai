$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $root ".local\services.json"
$tunnelStatePath = Join-Path $root ".local\tunnels.json"
$frontendTunnelStatePath = Join-Path $root ".local\frontend-tunnel.json"

if (-not (Test-Path $statePath)) {
  Write-Output "No running service state found."
  exit 0
}

try {
  $state = Get-Content $statePath -Raw | ConvertFrom-Json
} catch {
  Write-Output "State file is unreadable. Remove .local/services.json manually if needed."
  exit 1
}

$services = if ($state.services) { @($state.services) } else { @($state) }

foreach ($svc in $services) {
  if ($svc.pid) {
    Stop-Process -Id ([int]$svc.pid) -Force -ErrorAction SilentlyContinue
  }
}

Remove-Item $statePath -Force -ErrorAction SilentlyContinue

if (Test-Path $tunnelStatePath) {
  try {
    $tunnelState = Get-Content $tunnelStatePath -Raw | ConvertFrom-Json
    $tunnels = if ($tunnelState.tunnels) { @($tunnelState.tunnels) } else { @($tunnelState) }
    foreach ($tunnel in $tunnels) {
      if ($tunnel.pid) {
        Stop-Process -Id ([int]$tunnel.pid) -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {
    # Ignore malformed tunnel state file.
  }
  Remove-Item $tunnelStatePath -Force -ErrorAction SilentlyContinue
}

if (Test-Path $frontendTunnelStatePath) {
  try {
    $frontendTunnelState = Get-Content $frontendTunnelStatePath -Raw | ConvertFrom-Json
    if ($frontendTunnelState.pid) {
      Stop-Process -Id ([int]$frontendTunnelState.pid) -Force -ErrorAction SilentlyContinue
    }
  } catch {
    # Ignore malformed frontend tunnel state file.
  }
  Remove-Item $frontendTunnelStatePath -Force -ErrorAction SilentlyContinue
}

Write-Output "Stopped local stack processes."
