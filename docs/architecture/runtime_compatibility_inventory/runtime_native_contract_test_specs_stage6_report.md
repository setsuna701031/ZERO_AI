# Runtime Native Contract Test Specs Stage 6

Inventory-only extraction of native runtime contract test specifications.
This script does not modify runtime behavior.

## Summary

- native contract test specs: 66
- ZERO_PATCH residue: 0
- verification passed: True

## Owner domain counts

- `step_executor`: 38
- `runtime_authority`: 16
- `task_runner`: 12

## Next action counts

- `bind_compatibility_path_to_native_owner_test`: 53
- `extract_native_authority_contract_test`: 12
- `extract_planning_recovery_contract_test`: 1

## Suggested test files

- `tests/test_native_step_executor_contracts.py`: 38
- `tests/test_native_runtime_authority_contracts.py`: 16
- `tests/test_native_task_runner_contracts.py`: 12

## Verification

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_evidence_freeze.py`
```text
..........                                                               [100%]
10 passed in 0.31s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_execution_ownership_migration_contract.py`
```text
.....                                                                    [100%]
5 passed in 4.83s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mainline_freeze_contract.py`
```text
....                                                                     [100%]
4 passed in 0.82s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mode_propagation.py`
```text
....                                                                     [100%]
4 passed in 4.71s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runner_scheduler_boundary_survival.py`
```text
...                                                                      [100%]
3 passed in 3.00s
```
