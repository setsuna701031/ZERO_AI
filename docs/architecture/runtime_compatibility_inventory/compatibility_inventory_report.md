# Runtime Compatibility Inventory Audit

## Scope

Inventory-only audit for `legacy`, `fallback`, and `compatibility` references after Runtime Patch Consolidation.
This script does not modify runtime behavior.

## Summary

- inventory items: 1281
- ZERO_PATCH residue: 0
- verification passed: True

## Category counts

- `fallback_reference`: 412
- `legacy_reference`: 279
- `runtime_core_compatibility`: 268
- `compatibility_reference`: 201
- `fallback_planning_or_recovery`: 62
- `abi_compatibility`: 22
- `import_compatibility_guard`: 12
- `legacy_route`: 9
- `migration_bridge`: 9
- `migration_blocker`: 7

## Risk counts

- `low`: 926
- `medium`: 355

## Target file counts

- `core/runtime/execution_authority.py`: 12
- `core/runtime/task_runner.py`: 15
- `core/runtime/step_executor.py`: 41
- `core/tasks/scheduler.py`: 208
- `core/runtime/runtime_authority.py`: 3
- `core/runtime/runtime_session_resume.py`: 2

## Top files

- `core/tasks/scheduler.py`: 208
- `core/tasks/scheduler_execution_gateway.py`: 65
- `core/runtime/executor.py`: 59
- `core/runtime/task_runtime.py`: 54
- `core/agent/agent_loop.py`: 51
- `core/runtime/step_executor.py`: 41
- `core/tasks/runtime_repair_apply_transaction.py`: 40
- `core/tasks/execution_gateway.py`: 38
- `core/runtime/execution_landing_consistency.py`: 31
- `core/tasks/execution_gateway_runtime.py`: 28
- `core/agent/code_chain_controlled_self_edit_bridge.py`: 27
- `core/planning/planner.py`: 27
- `core/runtime/runtime_execution_result.py`: 25
- `core/tasks/planner_gateway_runtime.py`: 25
- `core/runtime/self_edit_mainline_convergence.py`: 21
- `core/runtime/runtime_compatibility.py`: 20
- `core/tasks/work_package_intake.py`: 19
- `core/runtime/runtime_evidence_authority.py`: 18
- `core/runtime/governed_mutation_runtime.py`: 16
- `core/runtime/task_runner.py`: 15
- `core/planning/task_replanner.py`: 13
- `core/memory/step_reflection_engine.py`: 12
- `core/runtime/execution_authority.py`: 12
- `core/runtime/runtime_recovery_execution_contract.py`: 12
- `core/system/llm_planner.py`: 12

## High/medium risk samples

- `core/agent/agent_loop.py:355` `legacy_route` `audit_for_retirement` — engineering_task_result.setdefault("legacy_direct_json_engineering_task_runner", True)
- `core/agent/agent_loop.py:431` `legacy_route` `audit_for_retirement` — "legacy_direct_json_engineering_task_runner": False,
- `core/agent/agent_loop.py:503` `legacy_route` `audit_for_retirement` — "legacy_direct_engineering_task_route": False,
- `core/agent/agent_loop.py:519` `legacy_route` `audit_for_retirement` — "legacy_direct_json_engineering_task_runner": False,
- `core/agent/agent_loop.py:608` `legacy_route` `audit_for_retirement` — "legacy_direct_json_engineering_task_runner": False,
- `core/agent/agent_loop.py:653` `legacy_route` `audit_for_retirement` — "legacy_direct_json_engineering_task_runner": False,
- `core/agent/agent_loop.py:688` `legacy_route` `audit_for_retirement` — result["legacy_direct_json_engineering_task_runner"] = bool(1)
- `core/agent/agent_loop.py:705` `legacy_route` `audit_for_retirement` — "legacy_direct_json_engineering_task_runner": bool(1),
- `core/agent/agent_loop.py:718` `legacy_route` `audit_for_retirement` — "legacy_direct_engineering_task_route": True,
- `core/agent/agent_loop.py:8166` `migration_blocker` `keep_as_blocker_signal` — failure_reason = "legacy_runtime_dispatcher_migration_required"
- `core/agent/agent_loop.py:8212` `migration_blocker` `keep_as_blocker_signal` — "legacy_runtime_dispatcher_migration_required": True,
- `core/agent/code_chain_controlled_self_edit_bridge.py:107` `fallback_planning_or_recovery` `contract_review_required` — "planner_owned_intent_routing": not fallback_used,
- `core/agent/code_chain_controlled_self_edit_bridge.py:115` `fallback_planning_or_recovery` `contract_review_required` — "planner_owned_intent_routing": not fallback_used,
- `core/agent/code_chain_controlled_self_edit_bridge.py:120` `migration_blocker` `keep_as_blocker_signal` — failure_reason = "legacy_runtime_dispatcher_migration_required"
- `core/agent/code_chain_controlled_self_edit_bridge.py:152` `fallback_planning_or_recovery` `contract_review_required` — "planner_owned_intent_routing": not fallback_used,
- `core/agent/code_chain_controlled_self_edit_bridge.py:159` `migration_blocker` `keep_as_blocker_signal` — "legacy_runtime_dispatcher_migration_required": True,
- `core/agent/code_chain_controlled_self_edit_bridge.py:169` `fallback_planning_or_recovery` `contract_review_required` — "planner_owned_intent_routing": not fallback_used,
- `core/agent/code_chain_controlled_self_edit_bridge.py:286` `fallback_planning_or_recovery` `contract_review_required` — execution["planner_owned_intent_routing"] = not fallback_used
- `core/agent/code_chain_controlled_self_edit_bridge.py:326` `fallback_planning_or_recovery` `contract_review_required` — "planner_owned_intent_routing": not fallback_used,
- `core/agent/code_chain_controlled_self_edit_bridge.py:346` `fallback_planning_or_recovery` `contract_review_required` — "planner_owned_intent_routing": not fallback_used,
- `core/agent/code_chain_controlled_self_edit_bridge.py:431` `fallback_planning_or_recovery` `contract_review_required` — "planner_owned_intent_routing": not fallback_used,
- `core/operator/codex_operator.py:240` `migration_blocker` `keep_as_blocker_signal` — return _blocked(current, "legacy_runtime_dispatcher_migration_required")
- `core/operator/verification_runner.py:48` `migration_blocker` `keep_as_blocker_signal` — stderr="legacy_runtime_dispatcher_migration_required",
- `core/planning/planner.py:55` `fallback_planning_or_recovery` `contract_review_required` — - generic_task -> fallback to generic planner path
- `core/planning/planner.py:2088` `fallback_planning_or_recovery` `contract_review_required` — fallback_task_name = self._infer_task_name(task_dir="", goal="planner_steps")
- `core/planning/planner_contract_trace.py:75` `fallback_planning_or_recovery` `contract_review_required` — "scheduler_planner_legacy_fallback_used": _optional_bool(
- `core/planning/planner_contract_trace.py:76` `fallback_planning_or_recovery` `contract_review_required` — safe_payload.get("scheduler_planner_legacy_fallback_used")
- `core/planning/planner_contract_trace.py:158` `fallback_planning_or_recovery` `contract_review_required` — if bool(item.get("scheduler_planner_legacy_fallback_used", False)):
- `core/planning/replanner.py:135` `fallback_planning_or_recovery` `contract_review_required` — "summary": "Fallback recovery plan generated after scheduler step failure.",
- `core/planning/task_replanner.py:34` `fallback_planning_or_recovery` `contract_review_required` — - 只有在外部沒有傳 planner 時，才 fallback 自建 Planner
- `core/planning/task_replanner.py:742` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "task_replanner_fallback",
- `core/planning/task_replanner.py:755` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "task_replanner_fallback",
- `core/planning/task_replanner.py:774` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "task_replanner_fallback",
- `core/planning/task_replanner.py:783` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "task_replanner_fallback",
- `core/planning/task_replanner.py:792` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "task_replanner_fallback",
- `core/planning/task_replanner.py:799` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "task_replanner_fallback",
- `core/planning/task_replanner.py:801` `fallback_planning_or_recovery` `contract_review_required` — "final_answer": "目前 fallback planner 還無法把這個 goal 轉成可執行 steps。",
- `core/runtime/aer_runtime_integration.py:849` `migration_blocker` `keep_as_blocker_signal` — "error": "legacy_runtime_dispatcher_migration_required",
- `core/runtime/artifact_step_bridge.py:153` `migration_bridge` `keep_until_native_runtime_complete` — "thin_bridge_is_compatibility_layer": True,
- `core/runtime/controlled_mutation_bridge.py:162` `migration_bridge` `keep_until_native_runtime_complete` — "thin_bridge_is_compatibility_layer": True,
- `core/runtime/controlled_mutation_bridge.py:475` `migration_bridge` `keep_until_native_runtime_complete` — "thin_bridge_is_compatibility_layer": True,
- `core/runtime/controlled_mutation_bridge.py:643` `migration_bridge` `keep_until_native_runtime_complete` — "thin_bridge_is_compatibility_layer": True,
- `core/runtime/execution_authority.py:74` `runtime_core_compatibility` `manual_review_before_removal` — if payload.get("descriptive_only") or payload.get("compatibility_authority_adapter"):
- `core/runtime/execution_authority.py:152` `runtime_core_compatibility` `manual_review_before_removal` — authority_source: str = "runtime_compatibility",
- `core/runtime/execution_authority.py:269` `runtime_core_compatibility` `manual_review_before_removal` — "legacy_task",
- `core/runtime/execution_authority.py:277` `runtime_core_compatibility` `manual_review_before_removal` — "legacy_step",
- `core/runtime/execution_authority.py:303` `runtime_core_compatibility` `manual_review_before_removal` — "compatibility_authority_adapter": not has_explicit_authority,
- `core/runtime/execution_authority.py:387` `runtime_core_compatibility` `manual_review_before_removal` — Compatibility policy: strict explicit denial is preserved, while sealed
- `core/runtime/execution_authority.py:388` `runtime_core_compatibility` `manual_review_before_removal` — TEST/SYSTEM/RUNTIME and traced legacy runtime paths may receive the missing
- `core/runtime/execution_authority.py:420` `runtime_core_compatibility` `manual_review_before_removal` — or {"source": authority_source or "runtime_authority_gate_compat"}
- `core/runtime/execution_authority.py:467` `runtime_core_compatibility` `manual_review_before_removal` — merged.setdefault("authority_policy", "runtime_authority_gate_compat")
- `core/runtime/execution_authority.py:472` `runtime_core_compatibility` `manual_review_before_removal` — "identity_id": "runtime:compat",
- `core/runtime/execution_authority.py:474` `runtime_core_compatibility` `manual_review_before_removal` — "source": "runtime_authority_gate_compat",
- `core/runtime/execution_authority.py:515` `runtime_core_compatibility` `manual_review_before_removal` — "compatibility_seal": "runtime_authority_gate_compat",
- `core/runtime/execution_authority_handoff.py:82` `migration_bridge` `keep_until_native_runtime_complete` — "thin_bridge_fallback_enabled": True,
- `core/runtime/executor.py:1758` `fallback_planning_or_recovery` `contract_review_required` — fallback_plan = self._build_fallback_replan_plan(
- `core/runtime/executor.py:1764` `fallback_planning_or_recovery` `contract_review_required` — replanned_plan = fallback_plan
- `core/runtime/executor.py:1768` `fallback_planning_or_recovery` `contract_review_required` — title="fallback replan used",
- `core/runtime/executor.py:1781` `fallback_planning_or_recovery` `contract_review_required` — message=f"replanned_steps={len(replanned_plan.get('steps', []))}, used_fallback={used_fallback}",
- `core/runtime/executor.py:1852` `fallback_planning_or_recovery` `contract_review_required` — def _build_fallback_replan_plan(
- `core/runtime/executor.py:1861` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "executor_fallback",
- `core/runtime/executor.py:1863` `fallback_planning_or_recovery` `contract_review_required` — "final_answer": "fallback replan generated",
- `core/runtime/executor.py:1869` `fallback_planning_or_recovery` `contract_review_required` — "message": "executor fallback created recovery file",
- `core/runtime/executor.py:1876` `fallback_planning_or_recovery` `contract_review_required` — "message": "executor fallback read recovery file",
- `core/runtime/executor.py:1891` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "executor_fallback",
- `core/runtime/executor.py:1893` `fallback_planning_or_recovery` `contract_review_required` — "final_answer": "fallback replan generated for failed read",
- `core/runtime/executor.py:1914` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "executor_fallback",
- `core/runtime/executor.py:1916` `fallback_planning_or_recovery` `contract_review_required` — "final_answer": "fallback replan generated for failed write",
- `core/runtime/executor.py:1929` `fallback_planning_or_recovery` `contract_review_required` — "planner_mode": "executor_fallback",
- `core/runtime/executor.py:1931` `fallback_planning_or_recovery` `contract_review_required` — "final_answer": "generic fallback replan generated",
- `core/runtime/executor.py:1937` `fallback_planning_or_recovery` `contract_review_required` — "message": "generic fallback recovery step",
- `core/runtime/governed_engineering_batch.py:202` `migration_bridge` `keep_until_native_runtime_complete` — "thin_bridge_is_compatibility_layer": True,
- `core/runtime/planner_runtime_dispatch.py:37` `fallback_planning_or_recovery` `contract_review_required` — def _safe_short_id(value: Any, fallback: str = "planner_runtime_task") -> str:
- `core/runtime/recovery_replay_closure.py:44` `fallback_planning_or_recovery` `contract_review_required` — def _normalize_task_id(task: Dict[str, Any], fallback: str = "recovery_replay_task") -> str:
- `core/runtime/runtime_native_scheduler.py:169` `runtime_core_compatibility` `manual_review_before_removal` — This does not rewrite legacy scheduler.py. It provides the migration surface:
- `core/runtime/runtime_plan_executor.py:336` `migration_bridge` `keep_until_native_runtime_complete` — "thin_bridge_is_compatibility_layer": True,
- `core/runtime/runtime_recovery_execution_contract.py:697` `fallback_planning_or_recovery` `contract_review_required` — def _fallback_plan_report_view(self, *, reason: str, source_failure: dict[str, Any]) -> RuntimeRecoveryPlanReportView:
- `core/runtime/runtime_recovery_execution_contract.py:699` `fallback_planning_or_recovery` `contract_review_required` — recovery_id="runtime-recovery-fallback",
- `core/runtime/runtime_recovery_integration.py:28` `fallback_planning_or_recovery` `contract_review_required` — def evaluate_recovery_governance(payload: dict[str, Any]) -> _FallbackGovernanceResult:
- `core/runtime/runtime_recovery_integration_seal.py:28` `fallback_planning_or_recovery` `contract_review_required` — def evaluate_recovery_governance(payload: dict[str, Any]) -> _FallbackGovernanceResult:

## Verification

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_evidence_freeze.py`
```text
..........                                                               [100%]
10 passed in 0.31s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_execution_ownership_migration_contract.py`
```text
.....                                                                    [100%]
5 passed in 4.73s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mainline_freeze_contract.py`
```text
....                                                                     [100%]
4 passed in 0.74s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mode_propagation.py`
```text
....                                                                     [100%]
4 passed in 4.56s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runner_scheduler_boundary_survival.py`
```text
...                                                                      [100%]
3 passed in 2.99s
```


## Outputs

- `docs/architecture/runtime_compatibility_inventory/compatibility_inventory.json`
- `docs/architecture/runtime_compatibility_inventory/compatibility_inventory_summary.json`
