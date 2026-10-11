[CmdletBinding()]
param(
  [switch]$RequireOpenAI
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$localEnvPath = Join-Path $root ".local\public-demo.env.ps1"
$python = Join-Path $root ".venv\Scripts\python.exe"
$runnerConfig = Join-Path $root "frontend\runner.config.json"
$runtimeConfigRel = "configs/idpo_research_config.json"
$localModel = "qwen3.5:9b"
try {
  $runtimeConfig = Get-Content -Raw (Join-Path $root $runtimeConfigRel) | ConvertFrom-Json
  if ($runtimeConfig.llm.local_model) {
    $localModel = [string]$runtimeConfig.llm.local_model
  }
} catch {
  # Fall back to the default model name; the preflight below reports a broken config.
}

$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$passes = New-Object System.Collections.Generic.List[string]

function Add-Pass([string]$Message) {
  if (-not $passes.Contains($Message)) {
    $passes.Add($Message) | Out-Null
  }
}

function Add-Warn([string]$Message) {
  if (-not $warnings.Contains($Message)) {
    $warnings.Add($Message) | Out-Null
  }
}

function Add-Fail([string]$Message) {
  if (-not $failures.Contains($Message)) {
    $failures.Add($Message) | Out-Null
  }
}

function Test-CommandAvailable([string]$Name) {
  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Find-ExistingPath([string[]]$Candidates) {
  foreach ($candidate in $Candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return $candidate
    }
  }
  return $null
}

if (Test-Path $localEnvPath) {
  . $localEnvPath
  Add-Pass "Loaded local demo environment from .local\public-demo.env.ps1"
} else {
  Add-Warn "Local demo environment file .local\public-demo.env.ps1 is missing"
}

if (Test-Path $python) {
  Add-Pass "Python virtual environment found at .venv\Scripts\python.exe"
} else {
  Add-Fail "Missing Python virtual environment at .venv\Scripts\python.exe"
}

if (Test-CommandAvailable "node") {
  Add-Pass "Node.js command found"
} else {
  Add-Fail "Node.js command not found"
}

if (Test-CommandAvailable "npm") {
  Add-Pass "npm command found"
} else {
  Add-Fail "npm command not found"
}

if (Test-Path $runnerConfig) {
  Add-Pass "frontend/runner.config.json found"
} else {
  Add-Fail "frontend/runner.config.json is missing"
}

if (Test-CommandAvailable "ollama") {
  Add-Pass "Ollama command found"
  $ollamaList = & ollama list 2>$null | Out-String
  if ($ollamaList -match "(?im)$([regex]::Escape($localModel))") {
    Add-Pass "Ollama model $localModel is available"
  } else {
    Add-Fail "Ollama model $localModel is missing (run: ollama pull $localModel)"
  }
} else {
  Add-Fail "Ollama command not found"
}

if (Test-CommandAvailable "cloudflared") {
  Add-Pass "cloudflared command found"
} else {
  $cloudflaredPath = Find-ExistingPath @(
    (Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe"),
    (Join-Path $env:ProgramFiles "cloudflared\cloudflared.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\cloudflared\cloudflared.exe")
  )
  if ($cloudflaredPath) {
    Add-Pass "cloudflared installed at $cloudflaredPath"
  } else {
    Add-Warn "cloudflared is not installed; public tunnel setup will need another reverse proxy or local-only access"
  }
}

if ($env:OPENAI_API_KEY) {
  Add-Pass "OPENAI_API_KEY is set"
} elseif ($RequireOpenAI) {
  Add-Fail "OPENAI_API_KEY is required but not set"
} else {
  Add-Warn "OPENAI_API_KEY is not set; cloud fallback will not work"
}

foreach ($port in 5432, 6379) {
  $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if ($conn) {
    Add-Pass "Port $port is listening"
  } else {
    Add-Warn "Port $port is not listening yet"
  }
}

if (Test-Path $python) {
  $previousPaddleCheck = $env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK
  $env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = "True"
  $rootPy = ($root -replace "\\", "\\\\")
  $preflightScript = @"
import sys
import warnings
sys.path.insert(0, r"$rootPy")
warnings.filterwarnings("ignore")
from idpo.core.config import load_config
from idpo.core.preflight import run_preflight
cfg = load_config("$runtimeConfigRel")
print("\n".join(run_preflight(cfg)))
"@
  $scriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("idpo_preflight_" + [System.Guid]::NewGuid().ToString("N") + ".py")
  $stdoutPath = Join-Path ([System.IO.Path]::GetTempPath()) ("idpo_preflight_stdout_" + [System.Guid]::NewGuid().ToString("N") + ".log")
  $stderrPath = Join-Path ([System.IO.Path]::GetTempPath()) ("idpo_preflight_stderr_" + [System.Guid]::NewGuid().ToString("N") + ".log")
  Set-Content -Path $scriptPath -Value $preflightScript -Encoding UTF8
  $proc = Start-Process `
    -FilePath $python `
    -ArgumentList "-W", "ignore", $scriptPath `
    -WorkingDirectory $root `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru `
    -NoNewWindow
  $proc.WaitForExit()
  $preflightOutput = if (Test-Path $stdoutPath) { Get-Content $stdoutPath -Raw } else { "" }
  $preflightError = if (Test-Path $stderrPath) { Get-Content $stderrPath -Raw } else { "" }
  Remove-Item $scriptPath, $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
  if ($null -eq $previousPaddleCheck) {
    Remove-Item Env:\PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK -ErrorAction SilentlyContinue
  } else {
    $env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = $previousPaddleCheck
  }

  $combinedPreflight = (($preflightError + "`n" + $preflightOutput).Trim())
  if ($combinedPreflight -match "Traceback" -or $combinedPreflight -match "ModuleNotFoundError" -or $combinedPreflight -match "SyntaxError") {
    Add-Fail "Python preflight execution failed: $combinedPreflight"
  } elseif ([string]::IsNullOrWhiteSpace($combinedPreflight)) {
    Add-Pass "IDPO preflight returned no warnings"
  } else {
    foreach ($line in ($combinedPreflight -split "`r?`n")) {
      if ([string]::IsNullOrWhiteSpace($line)) {
        continue
      }
      $normalizedLine = $line.Trim()
      if ($normalizedLine.StartsWith("- ")) {
        $normalizedLine = $normalizedLine.Substring(2).Trim()
      }
      if ($normalizedLine -match "Connectivity check to the model hoster has been skipped" -or $normalizedLine -match "^Preflight warnings:") {
        continue
      }
      if ($normalizedLine -match "OPENAI_API_KEY is not set") {
        if ($RequireOpenAI) {
          Add-Fail $normalizedLine
        } else {
          Add-Warn $normalizedLine
        }
      } elseif ($normalizedLine -match [regex]::Escape($localModel)) {
        Add-Fail $normalizedLine
      } elseif ($normalizedLine -match "paddleocr") {
        Add-Fail $normalizedLine
      } else {
        Add-Warn $normalizedLine
      }
    }
  }
}

if (Test-Path $python) {
  $runtimeChecks = @(
    @{
      Name = "torch runtime"
      Code = "import torch; print('ok')"
      FailurePrefix = "Torch runtime import failed"
    },
    @{
      Name = "sentence-transformers runtime"
      Code = "from sentence_transformers import SentenceTransformer; print('ok')"
      FailurePrefix = "SentenceTransformers import failed"
    },
    @{
      Name = "paddle OCR runtime"
      Code = "import paddleocr; print('ok')"
      FailurePrefix = "Paddle OCR runtime import failed"
    }
  )

  foreach ($runtimeCheck in $runtimeChecks) {
    $scriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("idpo_runtime_check_" + [System.Guid]::NewGuid().ToString("N") + ".py")
    $outPath = Join-Path ([System.IO.Path]::GetTempPath()) ("idpo_runtime_stdout_" + [System.Guid]::NewGuid().ToString("N") + ".log")
    $errPath = Join-Path ([System.IO.Path]::GetTempPath()) ("idpo_runtime_stderr_" + [System.Guid]::NewGuid().ToString("N") + ".log")
    Set-Content -Path $scriptPath -Value $runtimeCheck.Code -Encoding UTF8
    $proc = Start-Process `
      -FilePath $python `
      -ArgumentList $scriptPath `
      -WorkingDirectory $root `
      -RedirectStandardOutput $outPath `
      -RedirectStandardError $errPath `
      -PassThru `
      -NoNewWindow
    $proc.WaitForExit()
    $runtimeOut = if (Test-Path $outPath) { Get-Content $outPath -Raw } else { "" }
    $runtimeErr = if (Test-Path $errPath) { Get-Content $errPath -Raw } else { "" }
    Remove-Item $scriptPath, $outPath, $errPath -Force -ErrorAction SilentlyContinue

    $runtimeCombined = ($runtimeErr + "`n" + $runtimeOut).Trim()
    if ($proc.ExitCode -eq 0 -or $runtimeCombined -match "(?m)^ok\s*$") {
      Add-Pass "$($runtimeCheck.Name) is importable"
    } else {
      $details = $runtimeCombined
      if ($details.Length -gt 400) {
        $details = $details.Substring(0, 400)
      }
      Add-Fail "$($runtimeCheck.FailurePrefix): $details"
    }
  }
}

Write-Output "Public demo host readiness"
Write-Output "=========================="

if ($passes.Count -gt 0) {
  Write-Output ""
  Write-Output "Pass"
  foreach ($item in $passes) {
    Write-Output "- $item"
  }
}

if ($warnings.Count -gt 0) {
  Write-Output ""
  Write-Output "Warning"
  foreach ($item in $warnings) {
    Write-Output "- $item"
  }
}

if ($failures.Count -gt 0) {
  Write-Output ""
  Write-Output "Blocker"
  foreach ($item in $failures) {
    Write-Output "- $item"
  }
  exit 1
}

Write-Output ""
Write-Output "Host is ready for the supported public demo deployment path."
