# ZERO Operator Registry Deglobalization — Phase 1

## 目的

這包把分散在主線元件中的：

```text
builtins._zero_operator_completion_registry_v13
builtins._zero_operator_failure_registry_v14
```

集中封裝到：

```text
core/runtime/operator_registry_service.py
```

Phase 1 不改行為，只把直接讀寫 builtins 的依賴收斂成正式 Runtime Service。

## 覆蓋檔案

請從 ZIP 內依照路徑覆蓋：

```text
core/runtime/operator_registry_service.py
core/runtime/operator_integration_bridge.py
core/runtime/persistent_operator.py
core/runtime/runtime_recovery_executor.py
core/runtime/runtime_replay_engine.py
core/runtime/task_runner.py
core/tasks/scheduler.py
tests/test_operator_registry_service_deglobalization.py
```

## 驗證指令

```powershell
cd E:\zero_ai

python -m compileall core cli tests tools

python -m pytest `
tests/test_operator_registry_service_deglobalization.py `
tests/test_operator_session_bootstrap_contract.py `
tests/test_persistent_operator_integration_bridge.py `
tests/test_operator_runtime_survival_loop.py `
tests/test_governed_runtime_handoff_continuity.py `
tests/test_runner_scheduler_boundary_survival.py `
tests/test_agentloop_scheduler_lifecycle_continuity.py `
-q
```

如果這包過，再跑前面封板包：

```powershell
python -m pytest `
tests/test_engineering_task_runner_phase5.py `
tests/test_runtime_mainline_evidence_seal_contract.py `
tests/test_runtime_session_resume_identity_boundary.py `
tests/test_engineering_long_horizon_goal_flow.py `
tests/test_runtime_status_canonicalization_seal.py `
tests/test_runtime_status_write_authority_seal.py `
tests/test_runtime_status_ownership_inventory.py `
tests/test_aer_runtime_dispatcher_migration_closure.py `
tests/test_aer_terminal_authority_lineage_seal.py `
tests/test_aer_live_execution_lineage_subject_binding.py `
-q
```

## Non-Mainline Issue Reporting

這包沒有移除 legacy registry backing store。

原因是目前 PersistentOperator、ReplayEngine、RecoveryExecutor 仍依賴既有 readback 行為。
Phase 1 先收斂呼叫點；Phase 2 才能安全改成 session-local/runtime-local store。
