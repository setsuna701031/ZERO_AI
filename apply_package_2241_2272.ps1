param(
    [string]$RepoRoot = (Get-Location).Path
)

$ErrorActionPreference = "Stop"
$source = Join-Path $PSScriptRoot "package_2241_2272_files"
if (-not (Test-Path $source)) {
    throw "Package source folder not found: $source"
}

$files = @(
    "core/runtime/runtime_executor_invocation_preparation.py",
    "tests/test_runtime_executor_invocation_preparation_bundle.py",
    "docs/runtime_executor_invocation_preparation_review.md",
    "docs/runtime_executor_invocation_preparation_seal.md"
)

foreach ($relative in $files) {
    $src = Join-Path $source $relative
    $dst = Join-Path $RepoRoot $relative
    $dstDir = Split-Path $dst -Parent
    if (-not (Test-Path $dstDir)) {
        New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
    }
    Copy-Item -Path $src -Destination $dst -Force
}

$appendPath = Join-Path $source "docs/aer_evolution_v2_package_sequence_2241_2272_append.md"
$sequencePath = Join-Path $RepoRoot "docs/aer_evolution_v2_package_sequence.md"
if ((Test-Path $appendPath) -and (Test-Path $sequencePath)) {
    $appendText = Get-Content $appendPath -Raw
    $sequenceText = Get-Content $sequencePath -Raw
    if ($sequenceText -notlike "*Package 2241-2272: Runtime Executor Invocation Preparation Layer*") {
        Add-Content -Path $sequencePath -Value $appendText
    }
}

Write-Host "Applied Package 2241-2272: Runtime Executor Invocation Preparation Layer"
Write-Host "Run: python -m pytest tests/test_runtime_executor_invocation_preparation_bundle.py -q"
