$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $root ".local\services.json"

if (-not (Test-Path $statePath)) {
  Write-Output "No running service state found."
  exit 0
}

try {
  $services = Get-Content $statePath -Raw | ConvertFrom-Json
} catch {
  Write-Output "State file is unreadable. Remove .local/services.json manually if needed."
  exit 1
}

foreach ($svc in @($services)) {
  if ($svc.pid) {
    Stop-Process -Id ([int]$svc.pid) -Force -ErrorAction SilentlyContinue
  }
}

Remove-Item $statePath -Force -ErrorAction SilentlyContinue
Write-Output "Stopped local stack processes."
