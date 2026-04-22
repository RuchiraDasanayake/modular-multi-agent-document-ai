[CmdletBinding()]
param(
  [string]$FrontendUrl = "http://127.0.0.1:3000",
  [int]$TimeoutSec = 60,
  [switch]$ForceNew
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $root ".local"
$logDir = Join-Path $localDir "logs"
$statePath = Join-Path $localDir "frontend-tunnel.json"
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

function Test-HttpOk {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [int]$TimeoutSeconds = 10
  )

  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSeconds
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
  } catch {
    return $false
  }
}

function Stop-TrackedFrontendTunnel {
  param(
    [Parameter(Mandatory = $true)][string]$TunnelStatePath
  )

  if (Test-Path -LiteralPath $TunnelStatePath) {
    try {
      $state = Get-Content -LiteralPath $TunnelStatePath -Raw | ConvertFrom-Json
      if ($state.pid) {
        Stop-Process -Id ([int]$state.pid) -Force -ErrorAction SilentlyContinue
      }
    } catch {
      # Ignore malformed state file.
    }
    Remove-Item -LiteralPath $TunnelStatePath -Force -ErrorAction SilentlyContinue
  }

  Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -match '^cloudflared(\.exe)?$' -and
      $_.CommandLine -match [regex]::Escape($FrontendUrl)
    } |
    ForEach-Object {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Start-FrontendTunnel {
  param(
    [Parameter(Mandatory = $true)][string]$CloudflaredPath,
    [Parameter(Mandatory = $true)][string]$TargetUrl,
    [Parameter(Mandatory = $true)][string]$LogsRoot,
    [Parameter(Mandatory = $true)][int]$TimeoutSeconds
  )

  $outPath = Join-Path $LogsRoot "frontend.public.out.log"
  $errPath = Join-Path $LogsRoot "frontend.public.err.log"
  if (Test-Path -LiteralPath $outPath) { Remove-Item -LiteralPath $outPath -Force -ErrorAction SilentlyContinue }
  if (Test-Path -LiteralPath $errPath) { Remove-Item -LiteralPath $errPath -Force -ErrorAction SilentlyContinue }

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
    throw "Failed to acquire frontend quick tunnel URL. $details"
  }

  return [PSCustomObject]@{
    started_at = (Get-Date).ToString("o")
    pid = $proc.Id
    target_url = $TargetUrl
    public_url = $publicUrl
    out = $outPath
    err = $errPath
  }
}

if (-not (Test-HttpOk -Url $FrontendUrl -TimeoutSeconds 10)) {
  throw "Frontend is not reachable at $FrontendUrl. Start the frontend first."
}

if (-not $ForceNew -and (Test-Path -LiteralPath $statePath)) {
  try {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $existingPid = if ($state.pid) { Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue } else { $null }
    $existingUrl = if ($state.public_url) { [string]$state.public_url } else { "" }
    if ($existingPid -and $existingUrl -and (Test-HttpOk -Url $existingUrl -TimeoutSeconds 15)) {
      [Console]::Out.WriteLine("Frontend public URL already active.")
      [Console]::Out.WriteLine($existingUrl)
      return
    }
  } catch {
    # Ignore stale or malformed state file and start fresh.
  }
}

$cloudflared = Resolve-CloudflaredPath
Stop-TrackedFrontendTunnel -TunnelStatePath $statePath
$state = Start-FrontendTunnel -CloudflaredPath $cloudflared -TargetUrl $FrontendUrl -LogsRoot $logDir -TimeoutSeconds $TimeoutSec
$stateJson = $state | ConvertTo-Json -Depth 3
Set-Content -LiteralPath $statePath -Value $stateJson

if (-not (Test-Path -LiteralPath $statePath)) {
  Stop-TrackedFrontendTunnel -TunnelStatePath $statePath
  throw "Frontend tunnel started but state file was not written."
}

if (-not (Test-HttpOk -Url $state.public_url -TimeoutSeconds 20)) {
  Stop-TrackedFrontendTunnel -TunnelStatePath $statePath
  throw "Frontend tunnel started but public URL did not become reachable in time."
}

[Console]::Out.WriteLine("Started frontend public URL.")
[Console]::Out.WriteLine($state.public_url)
