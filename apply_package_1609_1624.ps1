$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "package_1609_1624_files"

if (!(Test-Path $source)) {
    throw "Package source folder not found: $source"
}

$targets = @(
    "core/runtime/runtime_execution_result_intake_gate.py",
    "core/runtime/runtime_result_validation_authority.py",
    "core/runtime/runtime_result_progress_apply_adapter.py",
    "core/runtime/runtime_execution_result_closure.py",
    "tests/test_runtime_execution_result_closure_bundle.py",
    "docs/contracts/runtime/runtime_execution_result_closure_v1.md",
    "docs/runtime_execution_result_closure_review.md",
    "docs/runtime_execution_result_closure_seal.md"
)

foreach ($relative in $targets) {
    $src = Join-Path $source $relative
    $dst = Join-Path (Get-Location) $relative
    $dir = Split-Path -Parent $dst
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
    Copy-Item -Path $src -Destination $dst -Force
}

$inventoryAppend = Join-Path $source "docs/contracts/runtime/inventory_append_1609_1624.md"
$inventory = Join-Path (Get-Location) "docs/contracts/runtime/inventory.md"
if (Test-Path $inventory) {
    $marker = "Runtime Execution Result Closure v1"
    $inventoryText = Get-Content $inventory -Raw
    if ($inventoryText -notmatch [regex]::Escape($marker)) {
        Add-Content -Path $inventory -Value (Get-Content $inventoryAppend -Raw)
    }
}

$sequenceAppend = Join-Path $source "docs/aer_evolution_v2_package_sequence_append_1609_1624.md"
$sequence = Join-Path (Get-Location) "docs/aer_evolution_v2_package_sequence.md"
if (Test-Path $sequence) {
    $marker = "Package 1609-1624"
    $sequenceText = Get-Content $sequence -Raw
    if ($sequenceText -notmatch [regex]::Escape($marker)) {
        Add-Content -Path $sequence -Value (Get-Content $sequenceAppend -Raw)
    }
}

Write-Host "Package 1609-1624 applied. Run: python -m pytest tests/test_runtime_execution_result_closure_bundle.py -q"
