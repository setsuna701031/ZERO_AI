$ErrorActionPreference = "Stop"

$inventory = "docs/contracts/runtime/inventory.md"
$inventoryEntry = "- Runtime Controlled Scheduler Dispatch Bundle v1: ``docs/contracts/runtime/runtime_controlled_scheduler_dispatch_v1.md``"
if (Test-Path $inventory) {
    $content = Get-Content $inventory -Raw
    if ($content -notlike "*Runtime Controlled Scheduler Dispatch Bundle v1*") {
        Add-Content -Path $inventory -Value "`n$inventoryEntry"
    }
}

$sequence = "docs/aer_evolution_v2_package_sequence.md"
$sequenceEntry = @"

## Package 1561-1576

Package 1561-1576 implements the Runtime Controlled Scheduler Dispatch Bundle.

Files added:
- core/runtime/runtime_scheduler_dispatch_bridge.py
- core/runtime/runtime_runnable_selection_admission.py
- core/runtime/runtime_executor_handoff_gate.py
- tests/test_runtime_controlled_scheduler_dispatch_bundle.py
- docs/contracts/runtime/runtime_controlled_scheduler_dispatch_v1.md
- docs/runtime_controlled_scheduler_dispatch_review.md
- docs/runtime_controlled_scheduler_dispatch_seal.md

Validation:
- python -m pytest tests/test_runtime_controlled_scheduler_dispatch_bundle.py -q

Final decision: GO for controlled scheduler dispatch path. Executor activation remains unimplemented.
"@
if (Test-Path $sequence) {
    $content = Get-Content $sequence -Raw
    if ($content -notlike "*Package 1561-1576*" -and $content -notlike "*Package 1561–1576*") {
        Add-Content -Path $sequence -Value $sequenceEntry
    }
}
