# Runtime Contract Promotion Stage 3

Inventory-only promotion classification for contracts extracted in Stage 2. This script does not modify runtime behavior.

## Summary

- source contract items: 330
- ZERO_PATCH residue: 0
- verification passed: True

## Promotion counts

- `temporary_bridge_contract`: 264
- `native_runtime_contract`: 66

## Domain counts

- `scheduler_contract`: 221
- `planner_contract`: 43
- `step_executor_contract`: 38
- `authority_contract`: 16
- `taskrunner_contract`: 12

## Next action counts

- `keep_bridge_until_native_owner_exists`: 264
- `extract_native_contract_tests`: 66

## Top files

- `core\tasks\scheduler.py`: 208
- `core\runtime\step_executor.py`: 41
- `core\runtime\executor.py`: 16
- `core\runtime\task_runner.py`: 14
- `core\runtime\execution_authority.py`: 12
- `core\agent\code_chain_controlled_self_edit_bridge.py`: 8
- `core\planning\task_replanner.py`: 8
- `core\tasks\planner_gateway_runtime.py`: 8
- `core\planning\planner_contract_trace.py`: 3
- `core\planning\planner.py`: 2
- `core\runtime\runtime_recovery_execution_contract.py`: 2
- `core\planning\replanner.py`: 1
- `core\runtime\planner_runtime_dispatch.py`: 1
- `core\runtime\recovery_replay_closure.py`: 1
- `core\runtime\runtime_native_scheduler.py`: 1
- `core\runtime\runtime_recovery_integration.py`: 1
- `core\runtime\runtime_recovery_integration_seal.py`: 1
- `core\runtime\runtime_state_machine.py`: 1
- `core\runtime\task_step_executor_adapter.py`: 1

## Verification

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_evidence_freeze.py`
```text
..........                                                               [100%]
10 passed in 0.30s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_execution_ownership_migration_contract.py`
```text
.....                                                                    [100%]
5 passed in 4.78s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mainline_freeze_contract.py`
```text
....                                                                     [100%]
4 passed in 0.76s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mode_propagation.py`
```text
....                                                                     [100%]
4 passed in 4.58s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runner_scheduler_boundary_survival.py`
```text
...                                                                      [100%]
3 passed in 2.99s
```

