#requires -Version 7.2
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'native_product_common.ps1')

function Assert-Test {
  param([bool]$Condition, [string]$Message)
  if (-not $Condition) { throw "FAIL: $Message" }
}

function Assert-Throws {
  param([scriptblock]$Action, [string]$Message)
  $threw = $false
  try { & $Action | Out-Null } catch { $threw = $true }
  Assert-Test $threw $Message
}

Assert-NativeWindows
$testDir = Join-Path $env:TEMP ('docai-native-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testDir | Out-Null
$configPath = Join-Path $testDir 'config.json'
$listener = $null
$sleepChild = $null
$sleepIdentity = $null
try {
  $base = @{
    repoRoot = 'C:\repo'
    runtimeRoot = $testDir
    pgBin = 'C:\pg\bin'
    pgData = 'C:\pg\data'
    postgresPort = 55432
    databaseUrl = 'postgresql://user:pass@127.0.0.1:55432/docai'
    jwtSecret = 'test-secret-1234567890123456789012345'
    adminPassword = 'long-test-password'
    dataDir = 'C:\data'
    frontendPort = 3000
    gatewayPort = 8000
    pythonPath = 'C:\repo\.venv\Scripts\python.exe'
  }
  $base | ConvertTo-Json | Set-Content -LiteralPath $configPath
  $config = Get-NativeConfig -ConfigPath $configPath
  Assert-Test ($config.gatewayPythonPath -eq $config.pythonPath) 'Gateway Python defaults to product Python.'
  Assert-Test ($config.postgresPort -eq 55432) 'Config port parsed.'

  $bad = $base.Clone(); $bad.Remove('jwtSecret')
  $bad | ConvertTo-Json | Set-Content -LiteralPath $configPath
  Assert-Throws { Get-NativeConfig -ConfigPath $configPath } 'Missing JWT secret rejected.'
  $bad = $base.Clone(); $bad.frontendPort = 8000
  $bad | ConvertTo-Json | Set-Content -LiteralPath $configPath
  Assert-Throws { Get-NativeConfig -ConfigPath $configPath } 'Duplicate ports rejected.'
  $bad = $base.Clone(); $bad.databaseUrl = 'postgresql://user:pass@localhost:55432/docai'
  $bad | ConvertTo-Json | Set-Content -LiteralPath $configPath
  Assert-Throws { Get-NativeConfig -ConfigPath $configPath } 'Non-loopback-address database URL rejected.'

  $base | ConvertTo-Json | Set-Content -LiteralPath $configPath
  $config = Get-NativeConfig -ConfigPath $configPath
  $startScript = Join-Path (Split-Path -Parent $PSScriptRoot) 'start_native_product.ps1'
  $status = & $startScript -ConfigPath $configPath -Status | ConvertFrom-Json
  Assert-Test (-not $status.services.postgres.tracked) 'Status does not adopt an untracked PostgreSQL process.'
  Assert-Test (-not $status.services.gateway.tracked) 'Status does not adopt an untracked gateway process.'
  Assert-Test (-not $status.services.frontend.tracked) 'Status does not adopt an untracked frontend process.'
  $identity = Get-NativeProcessIdentity -Id $PID
  Assert-Test (Test-NativeProcessIdentity $identity) 'Current process identity verified.'
  $state = @{ version = 1; services = @{ gateway = $identity }; signature = '' }
  Save-NativeState -Config $config -State $state
  $loaded = Get-NativeState -Config $config
  Assert-Test ($null -ne $loaded) 'Signed state can be reloaded.'
  Assert-Test ($loaded.services.gateway.startedUtc -is [string]) 'Reloaded start time stays canonical UTC text.'
  Assert-Test ($loaded.services.gateway.startedUtc -eq $identity.startedUtc) 'Reloaded start time preserves HMAC input.'
  $loaded.services.gateway = @{pid = $PID; executable = 'C:\fake.exe'; startedUtc = 'now'}
  $loaded | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $config.statePath
  Assert-Throws { Get-NativeState -Config $config } 'Tampered process state rejected.'

  $wrong = @{ pid = $identity.pid; executable = $identity.executable; startedUtc = '2000-01-01T00:00:00Z' }
  Assert-Test (-not (Test-NativeProcessIdentity $wrong)) 'PID reuse or altered start time rejected.'

  $sleepScript = Join-Path $testDir 'sleep.ps1'
  'Start-Sleep -Seconds 15' | Set-Content -LiteralPath $sleepScript
  $sleepChild = Start-Process -FilePath (Join-Path $PSHOME 'pwsh.exe') `
    -ArgumentList ('-NoProfile -File "' + $sleepScript + '"') -WindowStyle Hidden -PassThru
  $sleepIdentity = Get-NativeProcessIdentity -Id $sleepChild.Id
  Assert-Test ($null -ne $sleepIdentity) 'Harmless child process identity captured.'
  $descendants = @(Get-NativeDescendants -Root $identity)
  Assert-Test ($sleepChild.Id -in $descendants) 'UTC child is found beneath signed UTC parent.'

  $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
  $listener.Start()
  $port = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
  Assert-Throws { Assert-NativePortFree -Port $port } 'Occupied port is rejected, never killed.'
  Assert-Test (Test-NativePortOwnership -Port $port -Identity $identity) 'Current process owns its listener.'
  Assert-Test (-not (Test-NativePortOwnership -Port $port -Identity $wrong)) 'Wrong identity does not own listener.'
  Write-Output 'native_product.test.ps1: PASS'
} finally {
  if ($listener) { $listener.Stop() }
  if ($sleepIdentity -and (Test-NativeProcessIdentity $sleepIdentity)) {
    Stop-Process -Id $sleepIdentity.pid -Force -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath (Join-Path $testDir 'sleep.ps1') -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $configPath -Force -ErrorAction SilentlyContinue
  $statePath = Join-Path $testDir 'state\native-product.json'
  Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $testDir 'state') -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $testDir -Force -ErrorAction SilentlyContinue
}
