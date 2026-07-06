$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $Root "package_1577_1592_files"

if (!(Test-Path $Source)) {
    throw "Package source folder not found: $Source"
}

Copy-Item -Path (Join-Path $Source "*") -Destination (Get-Location) -Recurse -Force

$inventory = "docs/contracts/runtime/inventory.md"
if (Test-Path $inventory) {
    $text = Get-Content $inventory -Raw
    if ($text -notmatch "Runtime Controlled Executor Activation Bundle v1") {
        Add-Content $inventory "`n- Runtime Controlled Executor Activation Bundle v1: docs/contracts/runtime/runtime_controlled_executor_activation_v1.md"
    }
}

$sequence = "docs/aer_evolution_v2_package_sequence.md"
if (Test-Path $sequence) {
    $text = Get-Content $sequence -Raw
    if ($text -notmatch "Package 1577-1592") {
        Add-Content $sequence @"

## Package 1577-1592

Package 1577-1592: Runtime Controlled Executor Activation Bundle

Implemented the controlled executor activation data path:

- Runtime Executor Activation Admission
- Runtime Executor Activation Bridge
- Runtime Executor Result Intake Gate

Final decision: GO for controlled executor activation only. Actual executor execution remains gated and unimplemented.
"@
    }
}

Write-Host "Applied Package 1577-1592 Runtime Controlled Executor Activation Bundle"
