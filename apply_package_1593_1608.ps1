$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $Root "package_1593_1608_files"
if (-not (Test-Path $Source)) {
    throw "Package source folder not found: $Source"
}

$Targets = @(
    "core/runtime/runtime_controlled_executor_run_admission.py",
    "core/runtime/runtime_controlled_executor_run_bridge.py",
    "core/runtime/runtime_controlled_executor_result_intake.py",
    "tests/test_runtime_controlled_executor_run_bridge_bundle.py",
    "docs/contracts/runtime/runtime_controlled_executor_run_v1.md",
    "docs/runtime_controlled_executor_run_review.md",
    "docs/runtime_controlled_executor_run_seal.md"
)

foreach ($Rel in $Targets) {
    $Src = Join-Path $Source $Rel
    $Dst = Join-Path (Get-Location) $Rel
    $DstDir = Split-Path -Parent $Dst
    if (-not (Test-Path $DstDir)) {
        New-Item -ItemType Directory -Force -Path $DstDir | Out-Null
    }
    Copy-Item -Force $Src $Dst
}

$InventoryAppend = Join-Path $Source "docs/contracts/runtime/inventory_append.md"
$Inventory = Join-Path (Get-Location) "docs/contracts/runtime/inventory.md"
if (Test-Path $Inventory) {
    Add-Content -Path $Inventory -Value (Get-Content $InventoryAppend -Raw)
}

$SequenceAppend = Join-Path $Source "docs/aer_evolution_v2_package_sequence_append.md"
$Sequence = Join-Path (Get-Location) "docs/aer_evolution_v2_package_sequence.md"
if (Test-Path $Sequence) {
    Add-Content -Path $Sequence -Value (Get-Content $SequenceAppend -Raw)
}

Write-Host "Package 1593-1608 applied."
