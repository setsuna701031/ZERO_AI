$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "package_1625_1648_files"
if (!(Test-Path $source)) {
    throw "Package source folder not found: $source"
}

$repo = Get-Location
$paths = @(
    "core/runtime",
    "tests",
    "docs/contracts/runtime",
    "docs"
)
foreach ($path in $paths) {
    $target = Join-Path $repo $path
    if (!(Test-Path $target)) {
        New-Item -ItemType Directory -Force -Path $target | Out-Null
    }
}

Copy-Item -Force (Join-Path $source "core/runtime/runtime_autonomous_loop_activation.py") (Join-Path $repo "core/runtime/runtime_autonomous_loop_activation.py")
Copy-Item -Force (Join-Path $source "tests/test_runtime_autonomous_loop_activation_bundle.py") (Join-Path $repo "tests/test_runtime_autonomous_loop_activation_bundle.py")
Copy-Item -Force (Join-Path $source "docs/contracts/runtime/runtime_autonomous_loop_activation_v1.md") (Join-Path $repo "docs/contracts/runtime/runtime_autonomous_loop_activation_v1.md")
Copy-Item -Force (Join-Path $source "docs/runtime_autonomous_loop_activation_review.md") (Join-Path $repo "docs/runtime_autonomous_loop_activation_review.md")
Copy-Item -Force (Join-Path $source "docs/runtime_autonomous_loop_activation_seal.md") (Join-Path $repo "docs/runtime_autonomous_loop_activation_seal.md")

$inventory = Join-Path $repo "docs/contracts/runtime/inventory.md"
$inventoryAppend = Get-Content -Raw -Encoding UTF8 (Join-Path $source "docs/contracts/runtime/inventory.md.append")
if (Test-Path $inventory) {
    $current = Get-Content -Raw -Encoding UTF8 $inventory
    if ($current -notmatch "Runtime Autonomous Loop Activation v1") {
        Add-Content -Encoding UTF8 -Path $inventory -Value $inventoryAppend
    }
}

$sequence = Join-Path $repo "docs/aer_evolution_v2_package_sequence.md"
$sequenceAppend = Get-Content -Raw -Encoding UTF8 (Join-Path $source "docs/aer_evolution_v2_package_sequence.md.append")
if (Test-Path $sequence) {
    $current = Get-Content -Raw -Encoding UTF8 $sequence
    if ($current -notmatch "Package 1625-1648") {
        Add-Content -Encoding UTF8 -Path $sequence -Value $sequenceAppend
    }
}

Write-Host "Package 1625-1648 applied."
