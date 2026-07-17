# Runtime Compatibility Classification Stage 1

Inventory-only classification of medium-risk compatibility, fallback, and legacy references.
This script does not modify runtime behavior.

## Summary

- source inventory items: 1281
- medium items classified: 355
- ZERO_PATCH residue: 0
- verification passed: True

## Classification counts

- `needs_contract`: 330
- `retire_candidate`: 9
- `keep`: 9
- `blocker_signal`: 7

## Medium category counts

- `runtime_core_compatibility`: 268
- `fallback_planning_or_recovery`: 62
- `legacy_route`: 9
- `migration_bridge`: 9
- `migration_blocker`: 7

## Target hotspot counts

- `core/agent/agent_loop.py`: 11
- `core/runtime/execution_authority.py`: 12
- `core/runtime/step_executor.py`: 41
- `core/runtime/task_runner.py`: 14
- `core/tasks/scheduler.py`: 208

## Top medium files

- `core/tasks/scheduler.py`: 208
- `core/runtime/step_executor.py`: 41
- `core/runtime/executor.py`: 16
- `core/runtime/task_runner.py`: 14
- `core/runtime/execution_authority.py`: 12
- `core/agent/agent_loop.py`: 11
- `core/agent/code_chain_controlled_self_edit_bridge.py`: 10
- `core/planning/task_replanner.py`: 8
- `core/tasks/planner_gateway_runtime.py`: 8
- `core/planning/planner_contract_trace.py`: 3
- `core/runtime/controlled_mutation_bridge.py`: 3
- `core/planning/planner.py`: 2
- `core/runtime/runtime_recovery_execution_contract.py`: 2
- `core/operator/codex_operator.py`: 1
- `core/operator/verification_runner.py`: 1
- `core/planning/replanner.py`: 1
- `core/runtime/aer_runtime_integration.py`: 1
- `core/runtime/artifact_step_bridge.py`: 1
- `core/runtime/execution_authority_handoff.py`: 1
- `core/runtime/governed_engineering_batch.py`: 1
- `core/runtime/planner_runtime_dispatch.py`: 1
- `core/runtime/recovery_replay_closure.py`: 1
- `core/runtime/runtime_native_scheduler.py`: 1
- `core/runtime/runtime_plan_executor.py`: 1
- `core/runtime/runtime_recovery_integration.py`: 1

## Classification file breakdown

### `blocker_signal`
- `core/agent/agent_loop.py`: 2
- `core/agent/code_chain_controlled_self_edit_bridge.py`: 2
- `core/operator/codex_operator.py`: 1
- `core/operator/verification_runner.py`: 1
- `core/runtime/aer_runtime_integration.py`: 1

### `keep`
- `core/runtime/controlled_mutation_bridge.py`: 3
- `core/runtime/artifact_step_bridge.py`: 1
- `core/runtime/execution_authority_handoff.py`: 1
- `core/runtime/governed_engineering_batch.py`: 1
- `core/runtime/runtime_plan_executor.py`: 1
- `core/runtime/runtime_session.py`: 1
- `core/runtime/runtime_session_recovery_finalization.py`: 1

### `needs_contract`
- `core/tasks/scheduler.py`: 208
- `core/runtime/step_executor.py`: 41
- `core/runtime/executor.py`: 16
- `core/runtime/task_runner.py`: 14
- `core/runtime/execution_authority.py`: 12
- `core/agent/code_chain_controlled_self_edit_bridge.py`: 8
- `core/planning/task_replanner.py`: 8
- `core/tasks/planner_gateway_runtime.py`: 8
- `core/planning/planner_contract_trace.py`: 3
- `core/planning/planner.py`: 2
- `core/runtime/runtime_recovery_execution_contract.py`: 2
- `core/planning/replanner.py`: 1
- `core/runtime/planner_runtime_dispatch.py`: 1
- `core/runtime/recovery_replay_closure.py`: 1
- `core/runtime/runtime_native_scheduler.py`: 1

### `retire_candidate`
- `core/agent/agent_loop.py`: 9

## Verification

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_evidence_freeze.py`
```text
..........                                                               [100%]
10 passed in 0.31s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_execution_ownership_migration_contract.py`
```text
.....                                                                    [100%]
5 passed in 4.79s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mainline_freeze_contract.py`
```text
....                                                                     [100%]
4 passed in 0.78s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mode_propagation.py`
```text
....                                                                     [100%]
4 passed in 4.78s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runner_scheduler_boundary_survival.py`
```text
...                                                                      [100%]
3 passed in 3.03s
```

## Outputs

- `E:\zero_ai\docs\architecture\runtime_compatibility_inventory\compatibility_classification_stage1.json`
- `E:\zero_ai\docs\architecture\runtime_compatibility_inventory\compatibility_classification_stage1_summary.json`
