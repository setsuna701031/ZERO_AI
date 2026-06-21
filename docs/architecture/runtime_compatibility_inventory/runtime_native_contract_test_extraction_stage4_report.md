# Runtime Native Contract Test Extraction Stage 4

Inventory-only extraction for native runtime contracts. This script does not modify runtime behavior.

## Summary

- source contract items: 330
- native runtime contract items: 66
- ZERO_PATCH residue: 0
- verification passed: True

## Domain counts

- `step_executor_contract`: 38
- `authority_contract`: 16
- `taskrunner_contract`: 12

## Assertion hint counts

- `legacy_compatibility_path_has_native_owner_or_blocker`: 53
- `execution_authority_is_explicit_and_enforced`: 12
- `planning_or_recovery_fallback_has_contract_evidence`: 1

## Top source files

- `core/runtime/step_executor.py`: 41
- `core/runtime/execution_authority.py`: 12
- `core/runtime/task_runner.py`: 12
- `core/runtime/task_step_executor_adapter.py`: 1

## Recommended extraction order

1. authority_contract
2. step_executor_contract
3. taskrunner_contract
4. scheduler_contract
5. planner_contract

## Verification

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_evidence_freeze.py`
```text
..........                                                               [100%]
10 passed in 0.30s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_execution_ownership_migration_contract.py`
```text
.....                                                                    [100%]
5 passed in 4.66s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mainline_freeze_contract.py`
```text
....                                                                     [100%]
4 passed in 0.81s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mode_propagation.py`
```text
....                                                                     [100%]
4 passed in 4.46s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runner_scheduler_boundary_survival.py`
```text
...                                                                      [100%]
3 passed in 2.93s
```
