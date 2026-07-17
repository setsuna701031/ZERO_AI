$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "package_1649_1672_files"
if (!(Test-Path $source)) {
    throw "Package source folder not found: $source"
}

$files = @(
    "core/runtime/runtime_autonomous_execution_enablement.py",
    "tests/test_runtime_autonomous_execution_enablement_bundle.py",
    "docs/contracts/runtime/runtime_autonomous_execution_enablement_v1.md",
    "docs/runtime_autonomous_execution_enablement_review.md",
    "docs/runtime_autonomous_execution_enablement_seal.md"
)

foreach ($rel in $files) {
    $src = Join-Path $source $rel
    $dst = Join-Path (Get-Location) $rel
    $dir = Split-Path -Parent $dst
    if (!(Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Copy-Item -Force $src $dst
}

$inventory = Join-Path (Get-Location) "docs/contracts/runtime/inventory.md"
$inventoryAppend = Join-Path $source "docs/contracts/runtime/inventory_runtime_autonomous_execution_enablement_append.md"
if (Test-Path $inventory) {
    $text = Get-Content -Raw -Path $inventory
    if ($text -notmatch "Runtime Autonomous Execution Enablement v1") {
        Add-Content -Path $inventory -Value (Get-Content -Raw -Path $inventoryAppend)
    }
}

$sequence = Join-Path (Get-Location) "docs/aer_evolution_v2_package_sequence.md"
$sequenceAppend = Join-Path $source "docs/aer_evolution_v2_package_sequence_1649_1672_append.md"
if (Test-Path $sequence) {
    $text = Get-Content -Raw -Path $sequence
    if ($text -notmatch "Package 1649-1672") {
        Add-Content -Path $sequence -Value (Get-Content -Raw -Path $sequenceAppend)
    }
}

Write-Host "Package 1649-1672 applied."
