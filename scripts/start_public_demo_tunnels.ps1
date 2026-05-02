[CmdletBinding()]
param(
  [string]$FrontendUrl = "http://127.0.0.1:3000",
  [string]$ApiUrl = "http://127.0.0.1:8000",
  [int]$TimeoutSec = 90
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $root ".local"
$logDir = Join-Path $localDir "logs"
$statePath = Join-Path $localDir "tunnels.json"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Resolve-CloudflaredPath {
  $cmd = Get-Command "cloudflared" -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }

  $candidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe"),
    (Join-Path $env:ProgramFiles "cloudflared\cloudflared.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\cloudflared\cloudflared.exe")
  )

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return $candidate
    }
  }

  throw "cloudflared.exe was not found."
}

function Stop-TrackedTunnels {
  param(
    [Parameter(Mandatory = $true)][string]$TunnelStatePath
  )

  if (-not (Test-Path -LiteralPath $TunnelStatePath)) {
    return
  }

  try {
    $state = Get-Content -LiteralPath $TunnelStatePath -Raw | ConvertFrom-Json
  } catch {
    Remove-Item -LiteralPath $TunnelStatePath -Force -ErrorAction SilentlyContinue
    return
  }

  $entries = if ($state.tunnels) { @($state.tunnels) } else { @($state) }
  foreach ($entry in $entries) {
    if ($entry.pid) {
      Stop-Process -Id ([int]$entry.pid) -Force -ErrorAction SilentlyContinue
    }
  }

  Remove-Item -LiteralPath $TunnelStatePath -Force -ErrorAction SilentlyContinue
}

function Start-QuickTunnel {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$TargetUrl,
    [Parameter(Mandatory = $true)][string]$CloudflaredPath,
    [Parameter(Mandatory = $true)][string]$LogsRoot,
    [Parameter(Mandatory = $true)][int]$TimeoutSeconds
  )

  $outPath = Join-Path $LogsRoot "$Name.tunnel.out.log"
  $errPath = Join-Path $LogsRoot "$Name.tunnel.err.log"
  if (Test-Path $outPath) { Remove-Item $outPath -Force -ErrorAction SilentlyContinue }
  if (Test-Path $errPath) { Remove-Item $errPath -Force -ErrorAction SilentlyContinue }

  $proc = Start-Process `
    -FilePath $CloudflaredPath `
    -ArgumentList "tunnel", "--url", $TargetUrl, "--loglevel", "info", "--no-autoupdate" `
    -RedirectStandardOutput $outPath `
    -RedirectStandardError $errPath `
    -PassThru

  $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  $regex = [regex]"https://[-a-z0-9]+\.trycloudflare\.com"
  $publicUrl = $null

  while ([DateTime]::UtcNow -lt $deadline) {
    Start-Sleep -Seconds 2
    foreach ($logPath in @($outPath, $errPath)) {
      if (-not (Test-Path -LiteralPath $logPath)) {
        continue
      }
      $content = Get-Content -LiteralPath $logPath -Raw
      $match = $regex.Match($content)
      if ($match.Success) {
        $publicUrl = $match.Value
        break
      }
    }
    if ($publicUrl) {
      break
    }
    if ($proc.HasExited) {
      break
    }
  }

  if (-not $publicUrl) {
    $stderr = if (Test-Path -LiteralPath $errPath) { Get-Content -LiteralPath $errPath -Raw } else { "" }
    $stdout = if (Test-Path -LiteralPath $outPath) { Get-Content -LiteralPath $outPath -Raw } else { "" }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    $details = ($stderr + "`n" + $stdout).Trim()
    if ($details.Length -gt 800) {
      $details = $details.Substring(0, 800)
    }
    throw "Failed to acquire quick tunnel URL for $Name. $details"
  }

  return [PSCustomObject]@{
    name = $Name
    pid = $proc.Id
    target_url = $TargetUrl
    public_url = $publicUrl
    out = $outPath
    err = $errPath
  }
}

$cloudflared = Resolve-CloudflaredPath
Stop-TrackedTunnels -TunnelStatePath $statePath

try {
  $apiTunnel = Start-QuickTunnel -Name "api" -TargetUrl $ApiUrl -CloudflaredPath $cloudflared -LogsRoot $logDir -TimeoutSeconds $TimeoutSec
  $partialState = [PSCustomObject]@{
    started_at = (Get-Date).ToString("o")
    tunnels = @($apiTunnel)
  }
  $partialState | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath

  $frontendTunnel = Start-QuickTunnel -Name "frontend" -TargetUrl $FrontendUrl -CloudflaredPath $cloudflared -LogsRoot $logDir -TimeoutSeconds $TimeoutSec

  $state = [PSCustomObject]@{
    started_at = (Get-Date).ToString("o")
    tunnels = @($apiTunnel, $frontendTunnel)
  }
  $state | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath

  & (Join-Path $PSScriptRoot "start_public_demo_stack.ps1") -FrontendOrigin $frontendTunnel.public_url -ApiOrigin $apiTunnel.public_url
} catch {
  Stop-TrackedTunnels -TunnelStatePath $statePath
  throw
}

Write-Output "Started public demo quick tunnels."
Write-Output "Frontend URL: $($frontendTunnel.public_url)"
Write-Output "API URL: $($apiTunnel.public_url)"
