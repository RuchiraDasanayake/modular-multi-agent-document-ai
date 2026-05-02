[CmdletBinding()]
param(
  [string]$BaseUrl = "http://127.0.0.1:3000",
  [string]$SampleFile = "",
  [int]$TimeoutSec = 600,
  [int]$PollIntervalSec = 5
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $root "frontend"
$runnerConfigPath = Join-Path $frontendDir "runner.config.json"

function Get-JsonResponse {
  param(
    [Parameter(Mandatory = $true)][string]$Url
  )

  $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Get -TimeoutSec 30
  if ($response.StatusCode -ge 400) {
    throw "GET $Url failed with status $($response.StatusCode)"
  }
  return $response.Content | ConvertFrom-Json
}

function Resolve-RunnerPath {
  param(
    [Parameter(Mandatory = $true)][string]$BaseDir,
    [Parameter(Mandatory = $true)][string]$Value
  )

  return [System.IO.Path]::GetFullPath((Join-Path $BaseDir $Value))
}

function Get-DefaultSampleFile {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot
  )

  $candidates = @(
    (Join-Path $RepoRoot "idpo\benchmark\data\invoice_basic.txt"),
    (Join-Path $RepoRoot "demo_docs\demo_clean_text.json")
  )

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return $candidate
    }
  }

  throw "No default smoke-test sample file found."
}

function Get-ContentTypeForFile {
  param(
    [Parameter(Mandatory = $true)][string]$Path
  )

  switch ([System.IO.Path]::GetExtension($Path).ToLowerInvariant()) {
    ".json" { return "application/json" }
    ".txt" { return "text/plain" }
    ".pdf" { return "application/pdf" }
    ".png" { return "image/png" }
    ".jpg" { return "image/jpeg" }
    ".jpeg" { return "image/jpeg" }
    default { return "application/octet-stream" }
  }
}

function Start-SmokeRun {
  param(
    [Parameter(Mandatory = $true)][string]$BaseUrl,
    [Parameter(Mandatory = $true)][string]$SamplePath
  )

  $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
  if (-not $curl) {
    throw "curl.exe is required for the smoke upload path on this host."
  }

  $statusMarker = "HTTP_STATUS:"
  $curlOutput = & $curl.Source `
    -s `
    -w "`n$statusMarker%{http_code}`n" `
    -X POST "$BaseUrl/api/runs/start" `
    -F "adaptiveMode=adaptive_safe" `
    -F "shadowMode=false" `
    -F "report=true" `
    -F "files=@$SamplePath;type=$(Get-ContentTypeForFile -Path $SamplePath)"

  if ($LASTEXITCODE -ne 0) {
    throw "curl.exe failed to submit the smoke upload."
  }

  $curlText = ($curlOutput | Out-String).Trim()
  $markerIndex = $curlText.LastIndexOf($statusMarker)
  if ($markerIndex -lt 0) {
    throw "Smoke upload response did not include an HTTP status marker."
  }

  $body = $curlText.Substring(0, $markerIndex).Trim()
  $statusText = $curlText.Substring($markerIndex + $statusMarker.Length).Trim()
  $statusCode = 0
  [void][int]::TryParse($statusText, [ref]$statusCode)

  if ($statusCode -lt 200 -or $statusCode -ge 300) {
    throw "Run start failed with status ${statusCode}: $body"
  }

  if (-not $body) {
    throw "Run start returned an empty response body."
  }

  return $body | ConvertFrom-Json
}

function Assert-AnyPathExists {
  param(
    [Parameter(Mandatory = $true)][string[]]$Candidates,
    [Parameter(Mandatory = $true)][string]$Description
  )

  foreach ($candidate in $Candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return $candidate
    }
  }

  throw "Missing required artifact: $Description"
}

function Find-AnyPath {
  param(
    [Parameter(Mandatory = $true)][string[]]$Candidates
  )

  foreach ($candidate in $Candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return $candidate
    }
  }

  return $null
}

function Resolve-RunRoot {
  param(
    [Parameter(Mandatory = $true)]$Job,
    [Parameter(Mandatory = $true)][string]$RunsDir
  )

  if ($Job.runPath) {
    $candidate = [string]$Job.runPath
    if (Test-Path -LiteralPath $candidate) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  if (-not $Job.runId) {
    throw "Smoke test completed without resolving runId or runPath."
  }

  $fallback = Join-Path $RunsDir ([string]$Job.runId)
  if (Test-Path -LiteralPath $fallback) {
    return (Resolve-Path -LiteralPath $fallback).Path
  }

  throw "Run directory not found for runId '$($Job.runId)'."
}

if (-not (Test-Path -LiteralPath $runnerConfigPath)) {
  throw "Missing runner config at $runnerConfigPath"
}

$runnerConfig = Get-Content -LiteralPath $runnerConfigPath -Raw | ConvertFrom-Json
$runsDir = Resolve-RunnerPath -BaseDir $frontendDir -Value $runnerConfig.runsDir
$base = $BaseUrl.TrimEnd("/")
$resolvedSample = if ($SampleFile) {
  [System.IO.Path]::GetFullPath($SampleFile)
} else {
  Get-DefaultSampleFile -RepoRoot $root
}

if (-not (Test-Path -LiteralPath $resolvedSample)) {
  throw "Smoke-test sample file not found: $resolvedSample"
}

Write-Output "Public demo smoke test"
Write-Output "======================"
Write-Output "Frontend base URL: $base"
Write-Output "Sample file: $resolvedSample"

$status = Get-JsonResponse -Url "$base/api/system/status"
$failingChecks = @($status.checks | Where-Object { -not $_.ok })
if ($failingChecks.Count -gt 0) {
  $details = ($failingChecks | ForEach-Object { "$($_.id): $($_.detail)" }) -join "; "
  throw "System status check failed: $details"
}
Write-Output "System status checks passed."
$job = Start-SmokeRun -BaseUrl $base -SamplePath $resolvedSample
if (-not $job.jobId) {
  throw "Run start response did not include jobId."
}

Write-Output "Started job: $($job.jobId)"

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSec)
$jobStatus = $job
while ([DateTime]::UtcNow -lt $deadline) {
  Start-Sleep -Seconds $PollIntervalSec
  $jobStatus = Get-JsonResponse -Url "$base/api/jobs/$($job.jobId)"
  Write-Output "Job status: $($jobStatus.status)"

  if ($jobStatus.status -eq "success") {
    break
  }

  if ($jobStatus.status -eq "failed") {
    $tail = @($jobStatus.logs | Select-Object -Last 10) -join [Environment]::NewLine
    throw "Smoke job failed: $($jobStatus.error)`n$tail"
  }
}

if ($jobStatus.status -ne "success") {
  throw "Smoke job timed out after $TimeoutSec seconds."
}

$runRoot = Resolve-RunRoot -Job $jobStatus -RunsDir $runsDir
$primaryPath = Join-Path $runRoot "primary"
if (-not (Test-Path -LiteralPath $primaryPath)) {
  $primaryPath = $runRoot
}

Write-Output "Resolved run root: $runRoot"
Write-Output "Resolved primary path: $primaryPath"

[void](Assert-AnyPathExists -Candidates @(
  (Join-Path $runRoot "run.json"),
  (Join-Path $primaryPath "run.json")
) -Description "run.json")
[void](Assert-AnyPathExists -Candidates @(
  (Join-Path $runRoot "run_metadata.json"),
  (Join-Path $primaryPath "run_metadata.json")
) -Description "run_metadata.json")
[void](Assert-AnyPathExists -Candidates @(
  (Join-Path $runRoot "metrics.json"),
  (Join-Path $primaryPath "metrics.json")
) -Description "metrics.json")
[void](Assert-AnyPathExists -Candidates @(
  (Join-Path $runRoot "docs.xlsx"),
  (Join-Path $runRoot "docs.csv"),
  (Join-Path $primaryPath "docs.xlsx"),
  (Join-Path $primaryPath "docs.csv")
) -Description "docs export")
[void](Assert-AnyPathExists -Candidates @(
  (Join-Path $runRoot "run.xlsx"),
  (Join-Path $runRoot "run.csv"),
  (Join-Path $primaryPath "run.xlsx"),
  (Join-Path $primaryPath "run.csv")
) -Description "run export")

$fieldsArtifact = Find-AnyPath -Candidates @(
  (Join-Path $runRoot "fields.json"),
  (Join-Path $primaryPath "fields.json")
)
if ($fieldsArtifact) {
  Write-Output "Optional artifact present: $fieldsArtifact"
} else {
  Write-Output "Optional artifact absent: fields.json"
}

$entitiesArtifact = Find-AnyPath -Candidates @(
  (Join-Path $runRoot "entities.xlsx"),
  (Join-Path $runRoot "entities.csv"),
  (Join-Path $primaryPath "entities.xlsx"),
  (Join-Path $primaryPath "entities.csv")
)
if ($entitiesArtifact) {
  Write-Output "Optional artifact present: $entitiesArtifact"
} else {
  Write-Output "Optional artifact absent: entities export"
}

$docsRoot = Join-Path $primaryPath "docs"
if (-not (Test-Path -LiteralPath $docsRoot)) {
  throw "Missing docs directory under $primaryPath"
}

$docDir = Get-ChildItem -LiteralPath $docsRoot -Directory | Select-Object -First 1
if (-not $docDir) {
  throw "Smoke run produced no document directories under $docsRoot"
}

Write-Output "Resolved document directory: $($docDir.FullName)"

[void](Assert-AnyPathExists -Candidates @((Join-Path $docDir.FullName "input\manifest.json")) -Description "input manifest")
[void](Assert-AnyPathExists -Candidates @((Join-Path $docDir.FullName "dae\output.json")) -Description "DAE output")
[void](Assert-AnyPathExists -Candidates @((Join-Path $docDir.FullName "plan\primary.json")) -Description "plan output")
[void](Assert-AnyPathExists -Candidates @((Join-Path $docDir.FullName "preprocessing\ocr\text.json")) -Description "OCR text output")
[void](Assert-AnyPathExists -Candidates @((Join-Path $docDir.FullName "structuring\extracted.json")) -Description "structured extraction output")
[void](Assert-AnyPathExists -Candidates @((Join-Path $docDir.FullName "validation\results.json")) -Description "validation results")
[void](Assert-AnyPathExists -Candidates @((Join-Path $docDir.FullName "reward.json")) -Description "reward output")
[void](Assert-AnyPathExists -Candidates @((Join-Path $docDir.FullName "decision_chain.json")) -Description "decision chain output")
[void](Assert-AnyPathExists -Candidates @((Join-Path $docDir.FullName "provenance\transparency.json")) -Description "transparency output")

Write-Output ""
Write-Output "Smoke test passed."
Write-Output "run_id=$($jobStatus.runId)"
Write-Output "run_root=$runRoot"
Write-Output "doc_id=$($docDir.Name)"
