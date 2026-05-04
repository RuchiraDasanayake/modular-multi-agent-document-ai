[CmdletBinding()]
param(
  [string]$ManifestPath = "datasets/starter_pack_manifest.json"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$manifestFile = Join-Path $root $ManifestPath

if (-not (Test-Path -LiteralPath $manifestFile)) {
  throw "Dataset manifest not found at $manifestFile"
}

$dataRoot = if ($env:IDPO_DATA_DIR -and $env:IDPO_DATA_DIR.Trim()) {
  $env:IDPO_DATA_DIR.Trim()
} else {
  Join-Path (Split-Path $root -Parent) "idpo-data"
}

$datasetRoot = Join-Path $dataRoot "datasets\starter_pack"
New-Item -ItemType Directory -Force -Path $datasetRoot | Out-Null

$manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
$stagedItems = @()

foreach ($item in @($manifest.items)) {
  $split = [string]$item.split
  $sourceRelative = [string]$item.source_path
  $sourcePath = Join-Path $root $sourceRelative
  if (-not (Test-Path -LiteralPath $sourcePath)) {
    throw "Missing dataset source file: $sourceRelative"
  }

  $splitDir = Join-Path $datasetRoot $split
  New-Item -ItemType Directory -Force -Path $splitDir | Out-Null

  $targetName = Split-Path $sourcePath -Leaf
  $targetPath = Join-Path $splitDir $targetName
  Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force

  $stagedItems += [PSCustomObject]@{
    id = [string]$item.id
    split = $split
    format = [string]$item.format
    source_path = $sourceRelative
    staged_path = $targetPath
    tags = @($item.tags)
    expected_fields = @($item.expected_fields)
  }
}

$stagedManifest = [PSCustomObject]@{
  name = [string]$manifest.name
  description = [string]$manifest.description
  staged_at = (Get-Date).ToString("o")
  dataset_root = $datasetRoot
  item_count = $stagedItems.Count
  splits = @($manifest.splits)
  items = $stagedItems
}

$stagedManifestPath = Join-Path $datasetRoot "manifest.json"
$stagedManifest | ConvertTo-Json -Depth 6 | Set-Content -Path $stagedManifestPath

Write-Output "Staged starter dataset."
Write-Output "Dataset root: $datasetRoot"
Write-Output "Manifest: $stagedManifestPath"
Write-Output "Item count: $($stagedItems.Count)"
