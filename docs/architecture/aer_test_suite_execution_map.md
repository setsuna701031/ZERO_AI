# AER Test Suite Execution Map

Last measured: 2026-06-16

Purpose:
- Avoid blind full-suite retries while sealing AER authority/dispatcher work.
- Provide explicit pytest file groups for daily and full seal validation.
- Record slow zones and production-root-cause-sensitive zones without changing production or test contracts.

## Inventory

- Python test files under `tests`: 929
- Full-suite behavior observed during the dispatcher propagation sweep:
  - `python -m pytest tests -q -x` reached about 29% with no failure before a 900 second timeout.
  - Earlier full-suite runs exposed legacy expectations in planner/tool/mutation contracts; those are tracked below.

## Groups

### Authority / Seal

Test files:
- `tests/test_aer_runtime_dispatcher_migration_closure.py`
- `tests/test_aer_legacy_migration_closure.py`
- `tests/test_aer_terminal_authority_lineage_seal.py`
- `tests/test_aer_live_execution_lineage_subject_binding.py`
- `tests/test_aer_runtime_task_work_package_authority_seal.py`
- `tests/test_agent_execution_runtime_authority_seal.py`

Command:
```powershell
python -m pytest tests/test_aer_runtime_dispatcher_migration_closure.py tests/test_aer_legacy_migration_closure.py tests/test_aer_terminal_authority_lineage_seal.py tests/test_aer_live_execution_lineage_subject_binding.py tests/test_aer_runtime_task_work_package_authority_seal.py tests/test_agent_execution_runtime_authority_seal.py -q
```

Result:
- 39 passed
- Duration: 34.73s
- First failure: none
- AER authority related: yes

### Runtime / Dispatcher

Test files:
- `tests/test_runtime_autonomous_dispatch.py`
- `tests/test_runtime_dispatcher_execution_authority_bridge.py`
- `tests/test_runtime_scheduler_contract_seal.py`
- `tests/test_aer_runtime_contract_seal.py`
- `tests/test_persistent_runtime_orchestrator_contract.py`
- `tests/test_long_engineering_runtime_contract.py`

Command:
```powershell
python -m pytest tests/test_runtime_autonomous_dispatch.py tests/test_runtime_dispatcher_execution_authority_bridge.py tests/test_runtime_scheduler_contract_seal.py tests/test_aer_runtime_contract_seal.py tests/test_persistent_runtime_orchestrator_contract.py tests/test_long_engineering_runtime_contract.py -q
```

Result:
- 32 passed, 1 failed
- Duration: 5.54s
- First failure: `tests/test_runtime_scheduler_contract_seal.py::test_scheduler_boundary_preserves_previous_evidence_and_parent_identity`
- AER authority related: yes
- Classification for this map: production-root-cause-sensitive, not handled here

Failure note:
- `calls[0]` is missing because the expected runner call was not recorded.
- This should be investigated as a scheduler/runtime boundary issue, not as a dispatcher propagation legacy expectation.

### Agent Loop

Test files:
- `tests/test_agent_loop_planner_step_executor_bridge_contract.py`
- `tests/test_agent_loop_planner_runtime_dispatch_contract.py`
- `tests/test_agent_loop_persistent_runtime_route_contract.py`
- `tests/test_agent_loop_execution_boundary_seal.py`
- `tests/test_agent_loop_engineering_task_runner.py`
- `tests/test_agent_loop_engineering_goal_route.py`

Command:
```powershell
python -m pytest tests/test_agent_loop_planner_step_executor_bridge_contract.py tests/test_agent_loop_planner_runtime_dispatch_contract.py tests/test_agent_loop_persistent_runtime_route_contract.py tests/test_agent_loop_execution_boundary_seal.py tests/test_agent_loop_engineering_task_runner.py tests/test_agent_loop_engineering_goal_route.py -q
```

Result:
- 34 passed
- Duration: 13.54s
- First failure: none
- AER authority related: partial

### Scheduler

Test files:
- `tests/test_scheduler_execution_boundary_seal.py`
- `tests/test_scheduler_taskrunner_authority_propagation_contract.py`
- `tests/test_scheduler_runtime_ownership_closure.py`
- `tests/test_scheduler_dispatch_result_helpers.py`
- `tests/test_scheduler_execution_gateway.py`
- `tests/test_scheduler_runtime_payload_contract.py`

Command:
```powershell
python -m pytest tests/test_scheduler_execution_boundary_seal.py tests/test_scheduler_taskrunner_authority_propagation_contract.py tests/test_scheduler_runtime_ownership_closure.py tests/test_scheduler_dispatch_result_helpers.py tests/test_scheduler_execution_gateway.py tests/test_scheduler_runtime_payload_contract.py -q
```

Result:
- 54 passed, 4 failed, 8 subtests passed
- Duration: 2.44s
- First failure: `tests/test_scheduler_execution_boundary_seal.py::test_scheduler_side_effect_reaches_endpoint_through_taskrunner`
- AER authority related: yes
- Classification for this map: production-root-cause-sensitive, not handled here

Failure notes:
- `_RecordingEndpoint.calls` is empty for side-effect dispatch.
- Approved non-repair scheduler task remained `queued` instead of `finished`.
- TaskRunner authority context reported `taskrunner_propagation` instead of `taskrunner_delegation`.
- One side-effect dispatch result lacked expected `source`.

### Adaptive / Memory

Test files:
- `tests/test_adaptive_memory_integration.py`
- `tests/test_adaptive_resume_execution.py`
- `tests/test_adaptive_runtime_boundary.py`
- `tests/test_memory_architecture_contract.py`
- `tests/test_memory_context_builder.py`
- `tests/test_memory_repository.py`

Command:
```powershell
python -m pytest tests/test_adaptive_memory_integration.py tests/test_adaptive_resume_execution.py tests/test_adaptive_runtime_boundary.py tests/test_memory_architecture_contract.py tests/test_memory_context_builder.py tests/test_memory_repository.py -q
```

Result:
- 25 passed
- Duration: 19.94s
- First failure: none
- AER authority related: partial

### Repair-Chain

Test files:
- `tests/test_repair_chain_runtime.py`

Command:
```powershell
python -m pytest tests/test_repair_chain_runtime.py -q
```

Result:
- 62 passed
- Duration: 247.86s
- First failure: none
- AER authority related: partial

Slow-zone note:
- A broader repair-chain command with `tests/test_code_chain_repair_evidence_export.py`, `tests/test_code_chain_repair_result_propagation.py`, `tests/test_code_chain_controlled_self_edit_authority_seal.py`, and `tests/test_agent_loop_code_chain_controlled_self_edit_bridge.py` timed out at 240s after 49 passing test dots.
- Keep `tests/test_repair_chain_runtime.py` as its own slow shard.

### Goal / Planning / Portfolio

Test files:
- `tests/test_engineering_goal_runtime_bridge.py`
- `tests/test_engineering_goal_scheduler.py`
- `tests/test_engineering_portfolio_cycle.py`
- `tests/test_engineering_program_cycle.py`
- `tests/test_planner_runtime_dispatch_contract.py`
- `tests/test_planner_gateway_runtime.py`

Command:
```powershell
python -m pytest tests/test_engineering_goal_runtime_bridge.py tests/test_engineering_goal_scheduler.py tests/test_engineering_portfolio_cycle.py tests/test_engineering_program_cycle.py tests/test_planner_runtime_dispatch_contract.py tests/test_planner_gateway_runtime.py -q
```

Result:
- 35 passed
- Duration: 2.87s
- First failure: none
- AER authority related: partial

### Workflow / Tool / Mutation

Test files:
- `tests/test_aer_engineering_task_chain_contract.py`
- `tests/test_aer_multifile_engineering_workflow_contract.py`
- `tests/test_aer_planner_tool_registry_bridge_contract.py`
- `tests/test_aer_tool_write_verify_path_contract.py`
- `tests/test_controlled_mutation_authority_seal.py`
- `tests/test_controlled_mutation_bridge_landing.py`

Command:
```powershell
python -m pytest tests/test_aer_engineering_task_chain_contract.py tests/test_aer_multifile_engineering_workflow_contract.py tests/test_aer_planner_tool_registry_bridge_contract.py tests/test_aer_tool_write_verify_path_contract.py tests/test_controlled_mutation_authority_seal.py tests/test_controlled_mutation_bridge_landing.py -q
```

Result:
- 19 passed
- Duration: 92.73s
- First failure: none
- AER authority related: yes

Slow-zone note:
- `tests/test_aer_multifile_engineering_workflow_contract.py` is a known slow contributor; last isolated run was about 54s.
- `tests/test_aer_engineering_task_chain_contract.py` was about 27s isolated.

### Persistence / Checkpoint

Test files:
- `tests/test_persistence_runtime_contract.py`
- `tests/test_persistent_runtime_orchestrator_contract.py`
- `tests/test_runtime_session_resume_v1.py`
- `tests/test_runtime_replay_snapshot.py`
- `tests/test_long_engineering_runtime_contract.py`
- `tests/test_persistent_engineering_session_contract.py`

Command:
```powershell
python -m pytest tests/test_persistence_runtime_contract.py tests/test_persistent_runtime_orchestrator_contract.py tests/test_runtime_session_resume_v1.py tests/test_runtime_replay_snapshot.py tests/test_long_engineering_runtime_contract.py tests/test_persistent_engineering_session_contract.py -q
```

Result:
- 24 passed
- Duration: 1.16s
- First failure: none
- AER authority related: partial

## Known Slow Files

- `tests/test_repair_chain_runtime.py`: 62 passed in 247.86s.
- Workflow/tool/mutation shard: 19 passed in 92.73s.
- `tests/test_aer_multifile_engineering_workflow_contract.py`: about 54s isolated in the prior validation run.
- `tests/test_aer_terminal_authority_lineage_seal.py`: about 36s isolated in the prior validation run.
- `tests/test_aer_engineering_task_chain_contract.py`: about 27s isolated in the prior validation run.

## Known Legacy Expectation Files

These were updated during the dispatcher propagation legacy sweep to accept legal runtime-owned success:
- `tests/test_aer_planner_tool_registry_bridge_contract.py`
- `tests/test_aer_tool_write_verify_path_contract.py`
- `tests/test_controlled_mutation_authority_seal.py`

## Production-Root-Cause-Sensitive Files

Do not rewrite expectations in these files without root-cause analysis:
- `tests/test_runtime_scheduler_contract_seal.py`
- `tests/test_scheduler_execution_boundary_seal.py`
- `tests/test_scheduler_taskrunner_authority_propagation_contract.py`

Known sensitive symptoms:
- Scheduler side-effect path not reaching the endpoint recorder.
- TaskRunner delegation not being established from scheduler authority context.
- Scheduler task remaining queued during authority propagation tests.
- Runtime scheduler boundary not preserving previous evidence/parent identity through the expected runner call.

## Recommended Daily Validation Command

```powershell
python -m pytest tests/test_aer_runtime_dispatcher_migration_closure.py tests/test_aer_legacy_migration_closure.py tests/test_aer_terminal_authority_lineage_seal.py tests/test_aer_live_execution_lineage_subject_binding.py tests/test_aer_runtime_task_work_package_authority_seal.py tests/test_agent_execution_runtime_authority_seal.py -q
python -m pytest tests/test_aer_engineering_task_chain_contract.py tests/test_aer_multifile_engineering_workflow_contract.py tests/test_aer_planner_tool_registry_bridge_contract.py tests/test_aer_tool_write_verify_path_contract.py tests/test_controlled_mutation_authority_seal.py -q
python -m compileall core cli tests
git diff --check
```

## Recommended Full Seal Validation Command

Run these as separate shards so slow zones and scheduler-sensitive failures are visible:

```powershell
python -m pytest tests/test_aer_runtime_dispatcher_migration_closure.py tests/test_aer_legacy_migration_closure.py tests/test_aer_terminal_authority_lineage_seal.py tests/test_aer_live_execution_lineage_subject_binding.py tests/test_aer_runtime_task_work_package_authority_seal.py tests/test_agent_execution_runtime_authority_seal.py -q
python -m pytest tests/test_runtime_autonomous_dispatch.py tests/test_runtime_dispatcher_execution_authority_bridge.py tests/test_runtime_scheduler_contract_seal.py tests/test_aer_runtime_contract_seal.py tests/test_persistent_runtime_orchestrator_contract.py tests/test_long_engineering_runtime_contract.py -q
python -m pytest tests/test_agent_loop_planner_step_executor_bridge_contract.py tests/test_agent_loop_planner_runtime_dispatch_contract.py tests/test_agent_loop_persistent_runtime_route_contract.py tests/test_agent_loop_execution_boundary_seal.py tests/test_agent_loop_engineering_task_runner.py tests/test_agent_loop_engineering_goal_route.py -q
python -m pytest tests/test_scheduler_execution_boundary_seal.py tests/test_scheduler_taskrunner_authority_propagation_contract.py tests/test_scheduler_runtime_ownership_closure.py tests/test_scheduler_dispatch_result_helpers.py tests/test_scheduler_execution_gateway.py tests/test_scheduler_runtime_payload_contract.py -q
python -m pytest tests/test_adaptive_memory_integration.py tests/test_adaptive_resume_execution.py tests/test_adaptive_runtime_boundary.py tests/test_memory_architecture_contract.py tests/test_memory_context_builder.py tests/test_memory_repository.py -q
python -m pytest tests/test_repair_chain_runtime.py -q
python -m pytest tests/test_engineering_goal_runtime_bridge.py tests/test_engineering_goal_scheduler.py tests/test_engineering_portfolio_cycle.py tests/test_engineering_program_cycle.py tests/test_planner_runtime_dispatch_contract.py tests/test_planner_gateway_runtime.py -q
python -m pytest tests/test_aer_engineering_task_chain_contract.py tests/test_aer_multifile_engineering_workflow_contract.py tests/test_aer_planner_tool_registry_bridge_contract.py tests/test_aer_tool_write_verify_path_contract.py tests/test_controlled_mutation_authority_seal.py tests/test_controlled_mutation_bridge_landing.py -q
python -m pytest tests/test_persistence_runtime_contract.py tests/test_persistent_runtime_orchestrator_contract.py tests/test_runtime_session_resume_v1.py tests/test_runtime_replay_snapshot.py tests/test_long_engineering_runtime_contract.py tests/test_persistent_engineering_session_contract.py -q
python -m compileall core cli tests
git diff --check
```

## Non-Mainline Issues

- `pytest` and `python` are not available on PATH in this environment; use the bundled Python path or fix the environment.
- The repo `.venv` and `venv` point to a missing Python installation.
- Full suite currently exceeds practical interactive runtime; a 900s run reached about 29% with no failure.
- A failed persistence-map command used `tests/test_runtime_checkpoint*`; pytest did not expand it and returned `file or directory not found`. The corrected persistence shard uses explicit file names.
- Test execution can modify `runtime/evidence/evidence_records.jsonl`; account for this before staging changes.
