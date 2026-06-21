# Runtime Patch Consolidation Stage 1

## Current status

- ZERO_PATCH markers: 47
- touched files: 10
- backup directory: `E:\zero_ai\.zero_patch_consolidation_backup`

## Category map

- `authority`: 20
- `operator_session`: 12
- `recovery`: 2
- `replay_evidence`: 3
- `scheduler`: 10

## File map

### `core\runtime\execution_authority.py`
- L323: `ZERO_PATCH_RUNTIME_AUTHORITY_GATE_COMPAT_V1` (authority)
- L536: `ZERO_PATCH_RUNTIME_AUTHORITY_GATE_COMPAT_V2_END` (authority)

### `core\runtime\operator_integration_bridge.py`
- L221: `ZERO_PATCH_OPERATOR_REPLAY_EVIDENCE_V22` (replay_evidence)

### `core\runtime\operator_session_bootstrap.py`
- L266: `ZERO_PATCH_OPERATOR_BOOTSTRAP_TASK_RUNTIME_REF_V12` (operator_session)

### `core\runtime\persistent_operator.py`
- L380: `ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_COMPLETION_READBACK_V13B` (operator_session)
- L419: `ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILURE_READBACK_V14` (operator_session)
- L462: `ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILED_STEP_V15` (operator_session)
- L494: `ZERO_PATCH_OPERATOR_STATUS_RESUMABLE_V17` (operator_session)
- L531: `ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V18` (operator_session)
- L603: `ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V19` (operator_session)
- L660: `ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V20` (operator_session)
- L722: `ZERO_PATCH_OPERATOR_RECOVERY_PAYLOAD_V21` (recovery)
- L761: `ZERO_PATCH_OPERATOR_REPLAY_EVIDENCE_V22` (replay_evidence)

### `core\runtime\runtime_native_engineering_session.py`
- L498: `ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_COMPLETION_READBACK_V13B` (operator_session)
- L537: `ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILURE_READBACK_V14` (operator_session)
- L580: `ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_FAILED_STEP_V15` (operator_session)
- L612: `ZERO_PATCH_OPERATOR_STATUS_RESUMABLE_V17` (operator_session)

### `core\runtime\runtime_recovery_executor.py`
- L397: `ZERO_PATCH_OPERATOR_RECOVERY_PAYLOAD_V21` (recovery)

### `core\runtime\runtime_replay_engine.py`
- L1289: `ZERO_PATCH_OPERATOR_REPLAY_EVIDENCE_V22` (replay_evidence)

### `core\runtime\step_executor.py`
- L9523: `ZERO_PATCH_STEP_EXECUTOR_AUTHORITY_ENTRY_V1` (authority)
- L9656: `ZERO_PATCH_STEP_EXECUTOR_AUTHORITY_ENTRY_V2_END` (authority)

### `core\runtime\task_runner.py`
- L63: `ZERO_PATCH_TASKRUNNER_SCHEDULER_STEP_AUTHORITY_V1` (authority)
- L5478: `ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V1` (authority)
- L5588: `ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V2` (authority)
- L5687: `ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V3` (authority)
- L5725: `ZERO_PATCH_RUNTIME_GATE_FINAL_V4` (authority)
- L5795: `ZERO_PATCH_RUNTIME_GATE_FINAL_V5` (authority)
- L5865: `ZERO_PATCH_RUNTIME_GATE_FINAL_V6` (authority)
- L5925: `ZERO_PATCH_RUNTIME_GATE_FINAL_V7` (authority)
- L6000: `ZERO_PATCH_RUNTIME_GATE_FINAL_V8` (authority)

### `core\tasks\scheduler.py`
- L235: `ZERO_PATCH_TASKRUNNER_SCHEDULER_STEP_AUTHORITY_V1` (authority)
- L10415: `ZERO_PATCH_SCHEDULER_RUNTIME_GATE_FALLBACK_V1` (authority)
- L10495: `ZERO_PATCH_SCHEDULER_RUNTIME_GATE_FALLBACK_V2` (authority)
- L10572: `ZERO_PATCH_SCHEDULER_RUNTIME_GATE_FALLBACK_V3` (authority)
- L10643: `ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_FALLBACK_V4` (authority)
- L10709: `ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_DIRECT_HANDLER_V5` (authority)
- L10795: `ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_RESULT_SHAPE_V6` (authority)
- L10822: `ZERO_PATCH_SCHEDULER_OPERATOR_SESSION_COMPLETION_V7` (scheduler)
- L10893: `ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V8` (scheduler)
- L10980: `ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V9` (scheduler)
- L11051: `ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V10` (scheduler)
- L11157: `ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V11` (scheduler)
- L11246: `ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V12` (scheduler)
- L11310: `ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_READBACK_V13` (scheduler)
- L11334: `ZERO_PATCH_SCHEDULER_OPERATOR_FAILURE_READBACK_V14` (scheduler)
- L11366: `ZERO_PATCH_SCHEDULER_OPERATOR_FAILED_STEP_V15` (scheduler)
- L11400: `ZERO_PATCH_SCHEDULER_OPERATOR_FAILED_STEP_V16` (scheduler)

## Required consolidation order

1. Freeze current green state and keep `.zero_patch_consolidation_backup/` until all tests pass.
2. Consolidate `PersistentOperatorRuntime` first: session readback, failed checkpoint, recovery payload, replay evidence.
3. Consolidate `Scheduler` and `TaskRunner` authority handoff next.
4. Consolidate `StepExecutor` entry authority after runner/scheduler are stable.
5. Consolidate `execution_authority.py` compatibility policy last.
6. Remove every `ZERO_PATCH_*`, `_zero_patch_*`, and runtime `Class.method = wrapped` assignment.

## Verification results

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_evidence_freeze.py`
```text
..........                                                               [100%]
10 passed in 0.31s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_execution_ownership_migration_contract.py`
```text
.....                                                                    [100%]
5 passed in 4.74s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mainline_freeze_contract.py`
```text
....                                                                     [100%]
4 passed in 0.77s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mode_propagation.py`
```text
....                                                                     [100%]
4 passed in 5.63s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runner_scheduler_boundary_survival.py`
```text
...                                                                      [100%]
3 passed in 5.93s
```
