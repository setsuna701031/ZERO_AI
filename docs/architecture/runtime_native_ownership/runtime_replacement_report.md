# Runtime Replacement Inventory — Stage 11

Inventory and classification only. Stage 11 does not modify runtime production behavior.

## Summary

- Replacement total: 506
- Blocker count: 142
- Compatibility bridge count: 228
- Test-only count: 114
- Native-owner count: 22
- Manual-review count: 0
- ZERO_PATCH residue: 0
- Non-mainline issues: 139

## By classification

- `TEST_ONLY`: 114
- `NATIVE_OWNER`: 22
- `COMPATIBILITY_BRIDGE`: 228
- `BLOCKER`: 142
- `MANUAL_REVIEW`: 0

## By owner domain

- `scheduler`: 137
- `task_runner`: 48
- `step_executor`: 47
- `runtime_authority`: 0
- `planner`: 21
- `recovery`: 70
- `unknown`: 183

## By replacement kind

- `class_level_replacement`: 256
- `test_monkeypatch`: 108
- `compatibility_bridge_graft`: 66
- `runtime_owner_override`: 39
- `class_level_state_override`: 31
- `builtins_registry_bridge`: 6

## Top files

- `core/tasks/scheduler.py`: 86
- `core/runtime/workflow_runtime_session.py`: 68
- `core/runtime/task_runtime.py`: 62
- `tests/test_runtime_replay_execution_bridge.py`: 39
- `core/runtime/task_runner.py`: 36
- `core/runtime/step_executor.py`: 33
- `core/planning/planner.py`: 15
- `tests/test_scheduler_runtime_tail_regression.py`: 13
- `core/runtime/runtime_native_mainline.py`: 9
- `tests/test_scheduler_execution_gateway_basic_step_integration.py`: 9
- `tests/test_scheduler_execution_gateway_command_like_integration.py`: 9
- `tests/test_scheduler_execution_gateway_llm_step_integration.py`: 9
- `core/runtime/task_scheduler.py`: 7
- `core/agent/agent_loop.py`: 5
- `core/runtime/runtime_native_agent_loop.py`: 5
- `tests/test_aer_terminal_authority_lineage_seal.py`: 5
- `core/runtime/runtime_supervisor_bridge.py`: 4
- `core/runtime/work_package_operator.py`: 4
- `core/runtime/runtime_mainline_evidence_seal.py`: 3
- `core/tasks/scheduler_core/runtime_overlay_helpers.py`: 3
- `tests/test_agent_loop_engineering_goal_route.py`: 3
- `core/persona/runtime_bridge.py`: 2
- `core/runtime/agent_execution_runtime.py`: 2
- `core/runtime/runtime_dispatcher.py`: 2
- `core/runtime/runtime_evidence_registry.py`: 2

## Special mainline targets

### `RuntimeExecutionAuthorityGate.enforce` (0)

- No replacement detected.

### `Scheduler._handle_dispatch_result` (1)

- `core/tasks/scheduler.py:7782` `BLOCKER` — Scheduler._handle_dispatch_result = _scheduler_dispatch_compat_handle_dispatch_result

### `Scheduler._mark_repo_task_failed` (1)

- `core/tasks/scheduler.py:7788` `BLOCKER` — Scheduler._mark_repo_task_failed = _scheduler_repo_state_compat_mark_repo_task_failed

### `Scheduler._mark_repo_task_finished` (1)

- `core/tasks/scheduler.py:7787` `BLOCKER` — Scheduler._mark_repo_task_finished = _scheduler_repo_state_compat_mark_repo_task_finished

### `Scheduler.run_one_step` (25)

- `core/tasks/scheduler.py:9023` `BLOCKER` — Scheduler.run_one_step = _zero_v734_run_one_step
- `core/tasks/scheduler.py:9414` `BLOCKER` — Scheduler.run_one_step = _zero_v352_scheduler_run_one_step
- `core/tasks/scheduler.py:9579` `BLOCKER` — Scheduler.run_one_step = _zero_v7332_scheduler_run_one_step
- `core/tasks/scheduler.py:9784` `BLOCKER` — Scheduler.run_one_step = _zero_v7333_scheduler_run_one_step
- `core/tasks/scheduler.py:9950` `BLOCKER` — Scheduler.run_one_step = _zero_v7334_scheduler_run_one_step
- `core/tasks/scheduler.py:10166` `BLOCKER` — Scheduler.run_one_step = _zero_v7335_scheduler_run_one_step
- `core/tasks/scheduler.py:10352` `BLOCKER` — Scheduler.run_one_step = _zero_v7336_scheduler_run_one_step
- `core/tasks/scheduler.py:10493` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v1
- `core/tasks/scheduler.py:10570` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v2
- `core/tasks/scheduler.py:10641` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v3
- `core/tasks/scheduler.py:10707` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v4
- `core/tasks/scheduler.py:10793` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v5
- `core/tasks/scheduler.py:10820` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v6
- `core/tasks/scheduler.py:10891` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v7
- `core/tasks/scheduler.py:10978` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v8
- `core/tasks/scheduler.py:11049` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v9
- `core/tasks/scheduler.py:11155` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v10
- `core/tasks/scheduler.py:11244` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v11
- `core/tasks/scheduler.py:11308` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v12
- `core/tasks/scheduler.py:11332` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v13
- `core/tasks/scheduler.py:11364` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v14
- `core/tasks/scheduler.py:11398` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v15
- `core/tasks/scheduler.py:11432` `BLOCKER` — Scheduler.run_one_step = _zero_scheduler_run_one_step_v16
- `core/tasks/scheduler_core/runtime_overlay_helpers.py:226` `BLOCKER` — Scheduler.run_one_step = scheduler_run_one_step
- `core/tasks/scheduler_core/runtime_overlay_helpers.py:245` `BLOCKER` — Scheduler.run_one_step = scheduler_run_one_step

### `StepExecutor.execute_step` (10)

- `core/runtime/step_executor.py:6498` `BLOCKER` — StepExecutor.execute_step = _zero_v7313_execute_step_with_runtime_execution_result
- `core/runtime/step_executor.py:6867` `BLOCKER` — StepExecutor.execute_step = _zero_v7329_execute_step_final_public_abi
- `core/runtime/step_executor.py:7044` `BLOCKER` — StepExecutor.execute_step = _zero_v7330_execute_step_constitutional_probe
- `core/runtime/step_executor.py:7300` `BLOCKER` — StepExecutor.execute_step = _zero_v7331_execute_step_selective_activation
- `core/runtime/step_executor.py:7365` `BLOCKER` — StepExecutor.execute_step = _zero_v7332_execute_step_public_output_sanitizer
- `core/runtime/step_executor.py:7403` `BLOCKER` — StepExecutor.execute_step = _zero_v7333_execute_step_public_step_evidence_key_seal
- `core/runtime/step_executor.py:7778` `BLOCKER` — StepExecutor.execute_step = _zero_v7334_execute_step_with_pre_authority
- `core/runtime/step_executor.py:8464` `BLOCKER` — StepExecutor.execute_step = _zero_v811_execute_step_with_authority_closure
- `core/runtime/step_executor.py:9072` `BLOCKER` — StepExecutor.execute_step = _zero_direct_llm_execute_step_contract_seal
- `core/runtime/step_executor.py:9622` `BLOCKER` — StepExecutor.execute_step = _zero_boundary_execute_step

### `TaskRunner.run_task` (5)

- `core/runtime/task_runner.py:5643` `BLOCKER` — TaskRunner.run_task = _taskrunner_consolidated_run_task
- `core/runtime/task_runner.py:5692` `BLOCKER` — TaskRunner.run_task = _stage3b_run_task
- `core/runtime/task_runner.py:5889` `BLOCKER` — TaskRunner.run_task = _zero_stage3b_run_task_v2
- `core/runtime/task_runner.py:5991` `BLOCKER` — TaskRunner.run_task = _zero_stage3b_run_task_v3
- `core/runtime/task_runner.py:6045` `BLOCKER` — TaskRunner.run_task = _zero_stage3b_run_task_v4

### `TaskRunner.run_task_tick` (5)

- `core/runtime/task_runner.py:5630` `BLOCKER` — TaskRunner.run_task_tick = _taskrunner_consolidated_run_task_tick
- `core/runtime/task_runner.py:5683` `BLOCKER` — TaskRunner.run_task_tick = _stage3b_run_task_tick
- `core/runtime/task_runner.py:5875` `BLOCKER` — TaskRunner.run_task_tick = _zero_stage3b_run_task_tick_v2
- `core/runtime/task_runner.py:5982` `BLOCKER` — TaskRunner.run_task_tick = _zero_stage3b_run_task_tick_v3
- `core/runtime/task_runner.py:6036` `BLOCKER` — TaskRunner.run_task_tick = _zero_stage3b_run_task_tick_v4

### `RuntimeAuthority / execution_authority enforce path` (0)

- No replacement detected.

## Blockers

- `core/runtime/step_executor.py:4196` `step_executor` `StepExecutor._register_builtin_handlers` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:4221` `step_executor` `StepExecutor.__init__` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:4222` `step_executor` `StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:4366` `step_executor` `StepExecutor._register_builtin_handlers` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:4367` `step_executor` `StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:4576` `step_executor` `StepExecutor._register_builtin_handlers` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:4577` `step_executor` `StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:4587` `step_executor` `StepExecutor.CODE_CHAIN_WORKFLOW_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:5840` `step_executor` `StepExecutor.__init__` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:6037` `step_executor` `StepExecutor._attach_adapter_payload` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:6106` `step_executor` `StepExecutor._attach_adapter_payload` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:6166` `step_executor` `StepExecutor._attach_adapter_payload` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:6194` `step_executor` `StepExecutor._attach_adapter_payload` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:6498` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:6867` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:7044` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:7300` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:7365` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:7403` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:7775` `step_executor` `StepExecutor._classify_step_authority_requirement` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:7776` `step_executor` `StepExecutor._build_pre_execution_authority_decision` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:7777` `step_executor` `StepExecutor._attach_pre_execution_authority` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:7778` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:8464` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:8509` `step_executor` `StepExecutor.__init__` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:8731` `step_executor` `StepExecutor.__init__` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:8889` `step_executor` `StepExecutor._register_builtin_handlers` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:8890` `step_executor` `StepExecutor._handle_autonomous_repair_chain_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:9072` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/step_executor.py:9622` `step_executor` `StepExecutor.execute_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4589` `task_runner` `TaskRunner._run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4601` `task_runner` `TaskRunner.SIDE_EFFECT_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4605` `task_runner` `TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4624` `task_runner` `TaskRunner._determine_failure_type` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4634` `task_runner` `TaskRunner.SIDE_EFFECT_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4639` `task_runner` `TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4669` `task_runner` `TaskRunner._determine_failure_type` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4686` `task_runner` `TaskRunner.READ_ONLY_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4690` `task_runner` `TaskRunner.SIDE_EFFECT_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4695` `task_runner` `TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4696` `task_runner` `TaskRunner.CODE_CHAIN_WORKFLOW_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4722` `task_runner` `TaskRunner._determine_failure_type` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4983` `task_runner` `TaskRunner._zero_v800_build_observation` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4984` `task_runner` `TaskRunner._zero_v800_decide_from_observation` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4985` `task_runner` `TaskRunner._zero_v800_last_step_type` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4986` `task_runner` `TaskRunner._zero_v800_represents_failed_step_observation` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:4987` `task_runner` `TaskRunner._run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5082` `task_runner` `TaskRunner._finalize_public_result` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5179` `task_runner` `TaskRunner.__init__` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5180` `task_runner` `TaskRunner._persist_step_result_to_runtime_state` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5181` `task_runner` `TaskRunner._finalize_public_result` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5449` `task_runner` `TaskRunner._build_taskrunner_authority_context` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5476` `task_runner` `TaskRunner.run_task_adaptive` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5630` `task_runner` `TaskRunner.run_task_tick` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5643` `task_runner` `TaskRunner.run_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5645` `task_runner` `TaskRunner._runtime_gate_consolidated` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5683` `task_runner` `TaskRunner.run_task_tick` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5692` `task_runner` `TaskRunner.run_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5875` `task_runner` `TaskRunner.run_task_tick` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5889` `task_runner` `TaskRunner.run_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5982` `task_runner` `TaskRunner.run_task_tick` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:5991` `task_runner` `TaskRunner.run_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:6036` `task_runner` `TaskRunner.run_task_tick` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/runtime/task_runner.py:6045` `task_runner` `TaskRunner.run_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7664` `scheduler` `Scheduler._resolve_step_path` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7665` `scheduler` `Scheduler._resolve_read_path_with_fallback` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7666` `scheduler` `Scheduler._needs_scheduler_path_resolution` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7667` `scheduler` `Scheduler._normalize_step_scope` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7668` `scheduler` `Scheduler._resolve_guard_target_path` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7782` `scheduler` `Scheduler._handle_dispatch_result` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7783` `scheduler` `Scheduler._handle_missing_repo_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7784` `scheduler` `Scheduler._handle_run_one_step_exception` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7785` `scheduler` `Scheduler._finalize_dispatched_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7786` `scheduler` `Scheduler._extract_effective_status_and_answer` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7787` `scheduler` `Scheduler._mark_repo_task_finished` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7788` `scheduler` `Scheduler._mark_repo_task_failed` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7789` `scheduler` `Scheduler._mark_repo_task_queued` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7909` `scheduler` `Scheduler._plan_goal` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7910` `scheduler` `Scheduler._execute_simple_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7944` `scheduler` `Scheduler._execute_simple_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:7945` `scheduler` `Scheduler.SCHEDULER_BUILD` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8038` `scheduler` `Scheduler._is_repairable_failure` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8039` `scheduler` `Scheduler._normalize_replan_metadata` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8040` `scheduler` `Scheduler.REPAIRABLE_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8041` `scheduler` `Scheduler.SCHEDULER_BUILD` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8323` `scheduler` `Scheduler.cleanup_task_queue_hygiene` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8324` `scheduler` `Scheduler.tick` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8325` `scheduler` `Scheduler.get_queue_snapshot` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8326` `scheduler` `Scheduler.get_queue_rows` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8327` `scheduler` `Scheduler.SCHEDULER_BUILD` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8514` `scheduler` `Scheduler._find_active_duplicate_repair_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8515` `scheduler` `Scheduler.cleanup_task_queue_hygiene` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8516` `scheduler` `Scheduler.create_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8517` `scheduler` `Scheduler.tick` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8518` `scheduler` `Scheduler.SCHEDULER_BUILD` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8601` `scheduler` `Scheduler._is_repairable_failure` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8602` `scheduler` `Scheduler._normalize_replan_metadata` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8603` `scheduler` `Scheduler.REPAIRABLE_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8604` `scheduler` `Scheduler.CODE_CHAIN_WORKFLOW_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8605` `scheduler` `Scheduler.SCHEDULER_BUILD` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8639` `scheduler` `Scheduler._run_simple_task_tick` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8640` `scheduler` `Scheduler.CODE_CHAIN_WORKFLOW_STEP_TYPES` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:8641` `scheduler` `Scheduler.SCHEDULER_BUILD` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9023` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9024` `scheduler` `Scheduler._sync_runner_result_and_requeue_if_ready` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9025` `scheduler` `Scheduler.RETRYING_REPAIR_BRIDGE_VERSION` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9026` `scheduler` `Scheduler.SCHEDULER_BUILD` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9343` `scheduler` `Scheduler.approve_review_item` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9344` `scheduler` `Scheduler.reject_review_item` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9381` `scheduler` `Scheduler.get_review_queue` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9414` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9579` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9590` `scheduler` `Scheduler._is_repairable_failure` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9784` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9798` `scheduler` `Scheduler._is_repairable_failure` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9950` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:9964` `scheduler` `Scheduler._is_repairable_failure` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10166` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10180` `scheduler` `Scheduler._is_repairable_failure` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10352` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10366` `scheduler` `Scheduler._is_repairable_failure` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10406` `scheduler` `Scheduler._try_force_repo_edit_at_create_task` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10407` `scheduler` `Scheduler._create_task_record` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10493` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10570` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10641` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10707` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10793` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10820` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10891` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:10978` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:11049` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:11155` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:11244` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:11308` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:11332` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:11364` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:11398` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler.py:11432` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler_core/runtime_overlay_helpers.py:226` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler_core/runtime_overlay_helpers.py:227` `scheduler` `Scheduler._attach_autonomous_repair_chain_summary` — class-level function replacement changes authority/ownership/execution mainline behavior
- `core/tasks/scheduler_core/runtime_overlay_helpers.py:245` `scheduler` `Scheduler.run_one_step` — class-level function replacement changes authority/ownership/execution mainline behavior

## Non-Mainline Issue Report

These production findings are not one of the explicitly named Stage 11 mainline targets, but can still affect runtime ownership, authority, scheduler, task_runner, step_executor, or recovery/replay behavior.

- `core/tasks/scheduler.py`: 56
- `core/runtime/task_runner.py`: 25
- `core/runtime/step_executor.py`: 23
- `core/runtime/workflow_runtime_session.py`: 12
- `core/runtime/task_runtime.py`: 6
- `core/runtime/task_scheduler.py`: 3
- `core/runtime/runtime_native_mainline.py`: 2
- `core/agent/agent_loop.py`: 1
- `core/runtime/runtime_evidence_authority.py`: 1
- `core/runtime/runtime_mainline_evidence_seal.py`: 1
- `core/runtime/runtime_native_scheduler.py`: 1
- `core/runtime/runtime_recovery_executor.py`: 1
- `core/runtime/runtime_recovery_plan.py`: 1
- `core/runtime/runtime_replay_engine.py`: 1
- `core/runtime/scheduler_evidence_adapter.py`: 1
- `core/runtime/step_executor_evidence_adapter.py`: 1
- `core/runtime/task_step_executor_adapter.py`: 1
- `core/tasks/scheduler_core/code_chain_tick_replay_bridge.py`: 1
- `core/tasks/scheduler_core/runtime_overlay_helpers.py`: 1

### Detailed non-mainline findings

- `core/agent/agent_loop.py:110` `COMPATIBILITY_BRIDGE` `step_executor` `self.tool_registry` — self.tool_registry = kwargs.get("tool_registry") or getattr(step_executor, "tool_registry", None)
- `core/runtime/runtime_evidence_authority.py:89` `COMPATIBILITY_BRIDGE` `recovery` `self._payload` — self._payload: dict[str, Any] = { "runtime_version": RUNTIME_KERNEL_VERSION, "abi_version": RUNTIME_ABI_VERSION, "artifact_type": "runtime_evidence_authority", "evidence_id": evidence_id, "stdout": "", "stderr": "", "test_results": None, "mutation_summary": None, "verification_report": "", "runtime_traces": [], "impacted_plan": {}, "rollback_snapshot": {}, "runtime_state_transitions": [], "runtime_checkpoints": [], "runtime_events": [], "runtime_wal": {}, "runtime_budgets": {}, "runtime_memory_snapshots": [], "runtime_capability_graph": {}, "runtime_intent_evaluation": None, "runtime_isolation_boundary": None, "runtime_mutation_sandbox": None, "runtime_verification_sandbox": None, "runtime_seals": [], "runtime_integrity": [], "runtime_compatibility": [], "runtime_abi": [], "recovery": {}, }
- `core/runtime/runtime_mainline_evidence_seal.py:39` `COMPATIBILITY_BRIDGE` `scheduler` `self.scheduler_adapter` — self.scheduler_adapter = scheduler_adapter
- `core/runtime/runtime_native_mainline.py:348` `COMPATIBILITY_BRIDGE` `recovery` `self.supervisor_bridge` — self.supervisor_bridge = RuntimeSupervisorBridge.with_workspace( root / "supervisor_bridge", watchdog_lease_bridge=self.watchdog_lease_bridge, supervisor=self.supervisor, recovery_orchestrator=self.orchestrator, )
- `core/runtime/runtime_native_mainline.py:376` `COMPATIBILITY_BRIDGE` `recovery` `self.aer_integration` — self.aer_integration = AERRuntimeIntegration.with_workspace( root / "aer_integration", recovery_orchestrator=self.orchestrator, execution_fabric=self.execution_fabric, transaction_fabric=self.transaction_fabric, ownership_fabric=self.ownership_fabric, supervisor_bridge=self.supervisor_bridge, )
- `core/runtime/runtime_native_scheduler.py:192` `COMPATIBILITY_BRIDGE` `scheduler` `self.supervisor_bridge` — self.supervisor_bridge = supervisor_bridge or getattr(mainline, "supervisor_bridge", None)
- `core/runtime/runtime_recovery_executor.py:40` `COMPATIBILITY_BRIDGE` `recovery` `self.operator_bridge` — self.operator_bridge = operator_bridge
- `core/runtime/runtime_recovery_plan.py:647` `COMPATIBILITY_BRIDGE` `recovery` `self.policy_evaluator` — self.policy_evaluator = ( policy_evaluator if policy_evaluator is not None else _RuntimeRecoveryPolicyEvaluatorCompat() )
- `core/runtime/runtime_replay_engine.py:240` `COMPATIBILITY_BRIDGE` `recovery` `self.operator_bridge` — self.operator_bridge = operator_bridge
- `core/runtime/scheduler_evidence_adapter.py:23` `COMPATIBILITY_BRIDGE` `scheduler` `self.adapter_id` — self.adapter_id = self._validate_text("adapter_id", adapter_id)
- `core/runtime/step_executor.py:110` `COMPATIBILITY_BRIDGE` `step_executor` `self.tool_registry` — self.tool_registry = tool_registry
- `core/runtime/step_executor.py:116` `COMPATIBILITY_BRIDGE` `step_executor` `self.evidence_adapter` — self.evidence_adapter = evidence_adapter
- `core/runtime/step_executor.py:117` `COMPATIBILITY_BRIDGE` `step_executor` `self.operator_bridge` — self.operator_bridge = operator_bridge
- `core/runtime/step_executor.py:4196` `BLOCKER` `step_executor` `StepExecutor._register_builtin_handlers` — StepExecutor._register_builtin_handlers = _zero_v7_register_builtin_handlers
- `core/runtime/step_executor.py:4221` `BLOCKER` `step_executor` `StepExecutor.__init__` — StepExecutor.__init__ = _zero_v703_step_executor_init
- `core/runtime/step_executor.py:4222` `BLOCKER` `step_executor` `StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES` — StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES = {"code_chain_repair", "autonomous_code_repair"}
- `core/runtime/step_executor.py:4366` `BLOCKER` `step_executor` `StepExecutor._register_builtin_handlers` — StepExecutor._register_builtin_handlers = _zero_v710_register_builtin_handlers
- `core/runtime/step_executor.py:4367` `BLOCKER` `step_executor` `StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES` — StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES = {"code_chain_repair", "autonomous_code_repair", "code_chain_repair_preflight_failed"}
- `core/runtime/step_executor.py:4576` `BLOCKER` `step_executor` `StepExecutor._register_builtin_handlers` — StepExecutor._register_builtin_handlers = _zero_v730_register_builtin_handlers
- `core/runtime/step_executor.py:4577` `BLOCKER` `step_executor` `StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES` — StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES = { "code_chain_analyze", "code_chain_repair", "autonomous_code_repair", "code_chain_verify", "code_chain_repair_preflight_failed", }
- `core/runtime/step_executor.py:4587` `BLOCKER` `step_executor` `StepExecutor.CODE_CHAIN_WORKFLOW_STEP_TYPES` — StepExecutor.CODE_CHAIN_WORKFLOW_STEP_TYPES = set(getattr(StepExecutor, "CODE_CHAIN_REPAIR_STEP_TYPES", set())) | { "code_chain_analyze", "code_chain_repair", "autonomous_code_repair", "code_chain_verify", "code_chain_repair_preflight_failed", }
- `core/runtime/step_executor.py:5840` `BLOCKER` `step_executor` `StepExecutor.__init__` — StepExecutor.__init__ = _zero_v734_step_executor_init
- `core/runtime/step_executor.py:6037` `BLOCKER` `step_executor` `StepExecutor._attach_adapter_payload` — StepExecutor._attach_adapter_payload = _zero_v739_attach_adapter_payload
- `core/runtime/step_executor.py:6106` `BLOCKER` `step_executor` `StepExecutor._attach_adapter_payload` — StepExecutor._attach_adapter_payload = _zero_v7310_attach_adapter_payload
- `core/runtime/step_executor.py:6166` `BLOCKER` `step_executor` `StepExecutor._attach_adapter_payload` — StepExecutor._attach_adapter_payload = _zero_v7311_attach_adapter_payload
- `core/runtime/step_executor.py:6194` `BLOCKER` `step_executor` `StepExecutor._attach_adapter_payload` — StepExecutor._attach_adapter_payload = _zero_v7312_attach_adapter_payload
- `core/runtime/step_executor.py:7775` `BLOCKER` `step_executor` `StepExecutor._classify_step_authority_requirement` — StepExecutor._classify_step_authority_requirement = _zero_v7334_classify_step_authority_requirement
- `core/runtime/step_executor.py:7776` `BLOCKER` `step_executor` `StepExecutor._build_pre_execution_authority_decision` — StepExecutor._build_pre_execution_authority_decision = _zero_v7334_build_pre_execution_authority_decision
- `core/runtime/step_executor.py:7777` `BLOCKER` `step_executor` `StepExecutor._attach_pre_execution_authority` — StepExecutor._attach_pre_execution_authority = _zero_v7334_attach_pre_execution_authority
- `core/runtime/step_executor.py:8509` `BLOCKER` `step_executor` `StepExecutor.__init__` — StepExecutor.__init__ = _zero_v813_step_executor_init
- `core/runtime/step_executor.py:8731` `BLOCKER` `step_executor` `StepExecutor.__init__` — StepExecutor.__init__ = _zero_operator_step_executor_init
- `core/runtime/step_executor.py:8889` `BLOCKER` `step_executor` `StepExecutor._register_builtin_handlers` — StepExecutor._register_builtin_handlers = _zero_v2_step_executor_register_builtin_handlers
- `core/runtime/step_executor.py:8890` `BLOCKER` `step_executor` `StepExecutor._handle_autonomous_repair_chain_step` — StepExecutor._handle_autonomous_repair_chain_step = _zero_v2_autonomous_repair_chain_handler
- `core/runtime/step_executor_evidence_adapter.py:27` `COMPATIBILITY_BRIDGE` `step_executor` `self.adapter_id` — self.adapter_id = self._validate_text("adapter_id", adapter_id)
- `core/runtime/task_runner.py:4589` `BLOCKER` `task_runner` `TaskRunner._run_one_step` — TaskRunner._run_one_step = _zero_v702_task_runner_run_one_step
- `core/runtime/task_runner.py:4601` `BLOCKER` `task_runner` `TaskRunner.SIDE_EFFECT_STEP_TYPES` — TaskRunner.SIDE_EFFECT_STEP_TYPES = set(getattr(TaskRunner, "SIDE_EFFECT_STEP_TYPES", set())) | { "code_chain_repair", "autonomous_code_repair", }
- `core/runtime/task_runner.py:4605` `BLOCKER` `task_runner` `TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES` — TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES = {"code_chain_repair", "autonomous_code_repair"}
- `core/runtime/task_runner.py:4624` `BLOCKER` `task_runner` `TaskRunner._determine_failure_type` — TaskRunner._determine_failure_type = _zero_v703_task_runner_determine_failure_type
- `core/runtime/task_runner.py:4634` `BLOCKER` `task_runner` `TaskRunner.SIDE_EFFECT_STEP_TYPES` — TaskRunner.SIDE_EFFECT_STEP_TYPES = set(getattr(TaskRunner, "SIDE_EFFECT_STEP_TYPES", set())) | { "code_chain_repair", "autonomous_code_repair", "code_chain_repair_preflight_failed", }
- `core/runtime/task_runner.py:4639` `BLOCKER` `task_runner` `TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES` — TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES = set(getattr(TaskRunner, "CODE_CHAIN_REPAIR_STEP_TYPES", set())) | { "code_chain_repair", "autonomous_code_repair", "code_chain_repair_preflight_failed", }
- `core/runtime/task_runner.py:4669` `BLOCKER` `task_runner` `TaskRunner._determine_failure_type` — TaskRunner._determine_failure_type = _zero_v710_task_runner_determine_failure_type
- `core/runtime/task_runner.py:4686` `BLOCKER` `task_runner` `TaskRunner.READ_ONLY_STEP_TYPES` — TaskRunner.READ_ONLY_STEP_TYPES = set(getattr(TaskRunner, "READ_ONLY_STEP_TYPES", set())) | { "code_chain_analyze", "code_chain_verify", }
- `core/runtime/task_runner.py:4690` `BLOCKER` `task_runner` `TaskRunner.SIDE_EFFECT_STEP_TYPES` — TaskRunner.SIDE_EFFECT_STEP_TYPES = set(getattr(TaskRunner, "SIDE_EFFECT_STEP_TYPES", set())) | { "code_chain_repair", "autonomous_code_repair", "code_chain_repair_preflight_failed", }
- `core/runtime/task_runner.py:4695` `BLOCKER` `task_runner` `TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES` — TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES = set(getattr(TaskRunner, "CODE_CHAIN_REPAIR_STEP_TYPES", set())) | _ZERO_V731_TASK_RUNNER_CODE_CHAIN_WORKFLOW_STEP_TYPES
- `core/runtime/task_runner.py:4696` `BLOCKER` `task_runner` `TaskRunner.CODE_CHAIN_WORKFLOW_STEP_TYPES` — TaskRunner.CODE_CHAIN_WORKFLOW_STEP_TYPES = set(getattr(TaskRunner, "CODE_CHAIN_WORKFLOW_STEP_TYPES", set())) | _ZERO_V731_TASK_RUNNER_CODE_CHAIN_WORKFLOW_STEP_TYPES
- `core/runtime/task_runner.py:4722` `BLOCKER` `task_runner` `TaskRunner._determine_failure_type` — TaskRunner._determine_failure_type = _zero_v731_task_runner_determine_failure_type
- `core/runtime/task_runner.py:4983` `BLOCKER` `task_runner` `TaskRunner._zero_v800_build_observation` — TaskRunner._zero_v800_build_observation = _zero_v800_build_observation
- `core/runtime/task_runner.py:4984` `BLOCKER` `task_runner` `TaskRunner._zero_v800_decide_from_observation` — TaskRunner._zero_v800_decide_from_observation = _zero_v800_decide_from_observation
- `core/runtime/task_runner.py:4985` `BLOCKER` `task_runner` `TaskRunner._zero_v800_last_step_type` — TaskRunner._zero_v800_last_step_type = _zero_v800_last_step_type
- `core/runtime/task_runner.py:4986` `BLOCKER` `task_runner` `TaskRunner._zero_v800_represents_failed_step_observation` — TaskRunner._zero_v800_represents_failed_step_observation = _zero_v800_represents_failed_step_observation
- `core/runtime/task_runner.py:4987` `BLOCKER` `task_runner` `TaskRunner._run_one_step` — TaskRunner._run_one_step = _zero_v800_task_runner_run_one_step
- `core/runtime/task_runner.py:5082` `BLOCKER` `task_runner` `TaskRunner._finalize_public_result` — TaskRunner._finalize_public_result = _zero_v801_task_runner_finalize_public_result
- `core/runtime/task_runner.py:5179` `BLOCKER` `task_runner` `TaskRunner.__init__` — TaskRunner.__init__ = _zero_v810_taskrunner_init
- `core/runtime/task_runner.py:5180` `BLOCKER` `task_runner` `TaskRunner._persist_step_result_to_runtime_state` — TaskRunner._persist_step_result_to_runtime_state = _zero_v810_persist_step_result_to_runtime_state
- `core/runtime/task_runner.py:5181` `BLOCKER` `task_runner` `TaskRunner._finalize_public_result` — TaskRunner._finalize_public_result = _zero_v810_finalize_public_result
- `core/runtime/task_runner.py:5449` `BLOCKER` `task_runner` `TaskRunner._build_taskrunner_authority_context` — TaskRunner._build_taskrunner_authority_context = _zero_boundary_build_taskrunner_authority_context
- `core/runtime/task_runner.py:5476` `BLOCKER` `task_runner` `TaskRunner.run_task_adaptive` — TaskRunner.run_task_adaptive = _zero_run_task_adaptive
- `core/runtime/task_runner.py:5645` `BLOCKER` `task_runner` `TaskRunner._runtime_gate_consolidated` — TaskRunner._runtime_gate_consolidated = True
- `core/runtime/task_runner.py:6022` `COMPATIBILITY_BRIDGE` `task_runner` `builtins._zero_operator_failure_registry_v14` — setattr(builtins, '_zero_operator_failure_registry_v14', failures)
- `core/runtime/task_runtime.py:8973` `COMPATIBILITY_BRIDGE` `recovery` `TaskRuntime.build_governed_replay_aer_governance_core_seal` — TaskRuntime.build_governed_replay_aer_governance_core_seal = _zero_v916_build_governed_replay_aer_governance_core_seal
- `core/runtime/task_runtime.py:9149` `COMPATIBILITY_BRIDGE` `recovery` `TaskRuntime.build_governed_replay_aer_governance_core_seal` — TaskRuntime.build_governed_replay_aer_governance_core_seal = _zero_v917_build_governed_replay_aer_governance_core_seal
- `core/runtime/task_runtime.py:11054` `COMPATIBILITY_BRIDGE` `recovery` `TaskRuntime.reconstruct_replay_from_evidence_record` — TaskRuntime.reconstruct_replay_from_evidence_record = staticmethod(reconstruct_replay_from_evidence_record)
- `core/runtime/task_runtime.py:11056` `COMPATIBILITY_BRIDGE` `recovery` `TaskRuntime.replay_readonly_execution_from_registry` — TaskRuntime.replay_readonly_execution_from_registry = staticmethod(replay_readonly_execution_from_registry)
- `core/runtime/task_runtime.py:11058` `COMPATIBILITY_BRIDGE` `recovery` `TaskRuntime.build_replay_lineage` — TaskRuntime.build_replay_lineage = staticmethod(build_replay_lineage)
- `core/runtime/task_runtime.py:11060` `COMPATIBILITY_BRIDGE` `recovery` `TaskRuntime.evaluate_runtime_replay_stability` — TaskRuntime.evaluate_runtime_replay_stability = staticmethod(evaluate_runtime_replay_stability)
- `core/runtime/task_scheduler.py:55` `COMPATIBILITY_BRIDGE` `scheduler` `self.tool_registry` — self.tool_registry = tool_registry
- `core/runtime/task_scheduler.py:57` `COMPATIBILITY_BRIDGE` `step_executor` `self.task_step_executor_adapter` — self.task_step_executor_adapter = task_step_executor_adapter
- `core/runtime/task_scheduler.py:58` `COMPATIBILITY_BRIDGE` `step_executor` `self.step_executor_adapter` — self.step_executor_adapter = step_executor_adapter
- `core/runtime/task_step_executor_adapter.py:29` `COMPATIBILITY_BRIDGE` `step_executor` `self.tool_registry` — self.tool_registry = tool_registry
- `core/runtime/workflow_runtime_session.py:6836` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.build_constitutional_self_amendment_replay_record` — WorkflowRuntimeSessionManager.build_constitutional_self_amendment_replay_record = _zero_build_constitutional_self_amendment_replay_record
- `core/runtime/workflow_runtime_session.py:6837` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.attach_constitutional_self_amendment_replay_record` — WorkflowRuntimeSessionManager.attach_constitutional_self_amendment_replay_record = _zero_attach_constitutional_self_amendment_replay_record
- `core/runtime/workflow_runtime_session.py:7210` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.build_epoch_replay_continuity_record` — WorkflowRuntimeSessionManager.build_epoch_replay_continuity_record = _zero_build_epoch_replay_continuity_record
- `core/runtime/workflow_runtime_session.py:7211` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.attach_epoch_replay_continuity_record` — WorkflowRuntimeSessionManager.attach_epoch_replay_continuity_record = _zero_attach_epoch_replay_continuity_record
- `core/runtime/workflow_runtime_session.py:7535` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.build_long_horizon_governance_replay_record` — WorkflowRuntimeSessionManager.build_long_horizon_governance_replay_record = _zero_build_long_horizon_governance_replay_record
- `core/runtime/workflow_runtime_session.py:7536` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.attach_long_horizon_governance_replay_record` — WorkflowRuntimeSessionManager.attach_long_horizon_governance_replay_record = _zero_attach_long_horizon_governance_replay_record
- `core/runtime/workflow_runtime_session.py:7543` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.build_constitutional_archive_replay_continuity_record` — WorkflowRuntimeSessionManager.build_constitutional_archive_replay_continuity_record = _zero_build_constitutional_archive_replay_continuity_record
- `core/runtime/workflow_runtime_session.py:7544` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.attach_constitutional_archive_replay_continuity_record` — WorkflowRuntimeSessionManager.attach_constitutional_archive_replay_continuity_record = _zero_attach_constitutional_archive_replay_continuity_record
- `core/runtime/workflow_runtime_session.py:7899` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.build_runtime_replay_acceleration_index_record` — WorkflowRuntimeSessionManager.build_runtime_replay_acceleration_index_record = _zero_build_runtime_replay_acceleration_index_record
- `core/runtime/workflow_runtime_session.py:7900` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.attach_runtime_replay_acceleration_index_record` — WorkflowRuntimeSessionManager.attach_runtime_replay_acceleration_index_record = _zero_attach_runtime_replay_acceleration_index_record
- `core/runtime/workflow_runtime_session.py:8194` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.build_runtime_replay_window_record` — WorkflowRuntimeSessionManager.build_runtime_replay_window_record = _zero_build_runtime_replay_window_record
- `core/runtime/workflow_runtime_session.py:8195` `COMPATIBILITY_BRIDGE` `recovery` `WorkflowRuntimeSessionManager.attach_runtime_replay_window_record` — WorkflowRuntimeSessionManager.attach_runtime_replay_window_record = _zero_attach_runtime_replay_window_record
- `core/tasks/scheduler.py:406` `COMPATIBILITY_BRIDGE` `scheduler` `self.evidence_adapter` — self.evidence_adapter = evidence_adapter
- `core/tasks/scheduler.py:438` `COMPATIBILITY_BRIDGE` `step_executor` `self.step_executor` — self.step_executor = StepExecutor( workspace_root=self.workspace_dir, runtime_store=runtime_store, tool_registry=tool_registry, llm_client=self.llm_client, debug=debug, )
- `core/tasks/scheduler.py:7664` `BLOCKER` `scheduler` `Scheduler._resolve_step_path` — Scheduler._resolve_step_path = staticmethod(resolve_step_path)
- `core/tasks/scheduler.py:7665` `BLOCKER` `scheduler` `Scheduler._resolve_read_path_with_fallback` — Scheduler._resolve_read_path_with_fallback = staticmethod(resolve_read_path_with_fallback)
- `core/tasks/scheduler.py:7666` `BLOCKER` `scheduler` `Scheduler._needs_scheduler_path_resolution` — Scheduler._needs_scheduler_path_resolution = staticmethod(needs_scheduler_path_resolution)
- `core/tasks/scheduler.py:7667` `BLOCKER` `scheduler` `Scheduler._normalize_step_scope` — Scheduler._normalize_step_scope = staticmethod(normalize_step_scope)
- `core/tasks/scheduler.py:7668` `BLOCKER` `scheduler` `Scheduler._resolve_guard_target_path` — Scheduler._resolve_guard_target_path = _scheduler_path_compat_resolve_guard_target_path
- `core/tasks/scheduler.py:7783` `BLOCKER` `scheduler` `Scheduler._handle_missing_repo_task` — Scheduler._handle_missing_repo_task = _scheduler_dispatch_compat_handle_missing_repo_task
- `core/tasks/scheduler.py:7784` `BLOCKER` `scheduler` `Scheduler._handle_run_one_step_exception` — Scheduler._handle_run_one_step_exception = _scheduler_dispatch_compat_handle_run_one_step_exception
- `core/tasks/scheduler.py:7785` `BLOCKER` `scheduler` `Scheduler._finalize_dispatched_task` — Scheduler._finalize_dispatched_task = _scheduler_dispatch_compat_finalize_dispatched_task
- `core/tasks/scheduler.py:7786` `BLOCKER` `scheduler` `Scheduler._extract_effective_status_and_answer` — Scheduler._extract_effective_status_and_answer = _scheduler_repo_state_compat_extract_effective_status_and_answer
- `core/tasks/scheduler.py:7789` `BLOCKER` `scheduler` `Scheduler._mark_repo_task_queued` — Scheduler._mark_repo_task_queued = _scheduler_repo_state_compat_mark_repo_task_queued
- `core/tasks/scheduler.py:7909` `BLOCKER` `scheduler` `Scheduler._plan_goal` — Scheduler._plan_goal = _zero_v702_scheduler_plan_goal
- `core/tasks/scheduler.py:7910` `BLOCKER` `scheduler` `Scheduler._execute_simple_step` — Scheduler._execute_simple_step = _zero_v702_scheduler_execute_simple_step
- `core/tasks/scheduler.py:7944` `BLOCKER` `scheduler` `Scheduler._execute_simple_step` — Scheduler._execute_simple_step = _zero_v7335_scheduler_execute_simple_step_no_direct_mutation
- `core/tasks/scheduler.py:7945` `BLOCKER` `scheduler` `Scheduler.SCHEDULER_BUILD` — Scheduler.SCHEDULER_BUILD = "DAG_EXECUTE_SAFETY_LOCK_V8_CODE_CHAIN_RUNTIME_INTEGRATION_V7_2_2_PRE_ENQUEUE_REPAIR_FINGERPRINT_GATE"
- `core/tasks/scheduler.py:8038` `BLOCKER` `scheduler` `Scheduler._is_repairable_failure` — Scheduler._is_repairable_failure = _zero_v703_scheduler_is_repairable_failure
- `core/tasks/scheduler.py:8039` `BLOCKER` `scheduler` `Scheduler._normalize_replan_metadata` — Scheduler._normalize_replan_metadata = _zero_v703_scheduler_normalize_replan_metadata
- `core/tasks/scheduler.py:8040` `BLOCKER` `scheduler` `Scheduler.REPAIRABLE_STEP_TYPES` — Scheduler.REPAIRABLE_STEP_TYPES = set(getattr(Scheduler, "REPAIRABLE_STEP_TYPES", set())) | _ZERO_V703_BASE_REPAIRABLE_STEP_TYPES
- `core/tasks/scheduler.py:8041` `BLOCKER` `scheduler` `Scheduler.SCHEDULER_BUILD` — Scheduler.SCHEDULER_BUILD = "DAG_EXECUTE_SAFETY_LOCK_V8_CODE_CHAIN_RUNTIME_INTEGRATION_V7_2_0_QUEUE_HYGIENE"
- `core/tasks/scheduler.py:8323` `BLOCKER` `scheduler` `Scheduler.cleanup_task_queue_hygiene` — Scheduler.cleanup_task_queue_hygiene = _zero_v724_cleanup_task_queue_hygiene
- `core/tasks/scheduler.py:8324` `BLOCKER` `scheduler` `Scheduler.tick` — Scheduler.tick = _zero_v724_tick
- `core/tasks/scheduler.py:8325` `BLOCKER` `scheduler` `Scheduler.get_queue_snapshot` — Scheduler.get_queue_snapshot = _zero_v724_get_queue_snapshot
- `core/tasks/scheduler.py:8326` `BLOCKER` `scheduler` `Scheduler.get_queue_rows` — Scheduler.get_queue_rows = _zero_v724_get_queue_rows
- `core/tasks/scheduler.py:8327` `BLOCKER` `scheduler` `Scheduler.SCHEDULER_BUILD` — Scheduler.SCHEDULER_BUILD = "DAG_EXECUTE_SAFETY_LOCK_V8_CODE_CHAIN_RUNTIME_INTEGRATION_V7_2_4_REPAIR_TASK_EXPIRATION_CLEANUP"
- `core/tasks/scheduler.py:8514` `BLOCKER` `scheduler` `Scheduler._find_active_duplicate_repair_task` — Scheduler._find_active_duplicate_repair_task = _zero_v726_find_active_duplicate_repair_task
- `core/tasks/scheduler.py:8515` `BLOCKER` `scheduler` `Scheduler.cleanup_task_queue_hygiene` — Scheduler.cleanup_task_queue_hygiene = _zero_v726_cleanup_task_queue_hygiene
- `core/tasks/scheduler.py:8516` `BLOCKER` `scheduler` `Scheduler.create_task` — Scheduler.create_task = _zero_v726_create_task
- `core/tasks/scheduler.py:8517` `BLOCKER` `scheduler` `Scheduler.tick` — Scheduler.tick = _zero_v726_tick
- `core/tasks/scheduler.py:8518` `BLOCKER` `scheduler` `Scheduler.SCHEDULER_BUILD` — Scheduler.SCHEDULER_BUILD = "DAG_EXECUTE_SAFETY_LOCK_V8_CODE_CHAIN_RUNTIME_INTEGRATION_V7_2_6_REPAIR_ENQUEUE_LOCK_LIFECYCLE"
- `core/tasks/scheduler.py:8601` `BLOCKER` `scheduler` `Scheduler._is_repairable_failure` — Scheduler._is_repairable_failure = _zero_v731_scheduler_is_repairable_failure
- `core/tasks/scheduler.py:8602` `BLOCKER` `scheduler` `Scheduler._normalize_replan_metadata` — Scheduler._normalize_replan_metadata = _zero_v731_scheduler_normalize_replan_metadata
- `core/tasks/scheduler.py:8603` `BLOCKER` `scheduler` `Scheduler.REPAIRABLE_STEP_TYPES` — Scheduler.REPAIRABLE_STEP_TYPES = set(getattr(Scheduler, "REPAIRABLE_STEP_TYPES", set())) | _ZERO_V731_BASE_REPAIRABLE_STEP_TYPES
- `core/tasks/scheduler.py:8604` `BLOCKER` `scheduler` `Scheduler.CODE_CHAIN_WORKFLOW_STEP_TYPES` — Scheduler.CODE_CHAIN_WORKFLOW_STEP_TYPES = set(getattr(Scheduler, "CODE_CHAIN_WORKFLOW_STEP_TYPES", set())) | _ZERO_V731_CODE_CHAIN_WORKFLOW_STEP_TYPES
- `core/tasks/scheduler.py:8605` `BLOCKER` `scheduler` `Scheduler.SCHEDULER_BUILD` — Scheduler.SCHEDULER_BUILD = "DAG_EXECUTE_SAFETY_LOCK_V8_CODE_CHAIN_RUNTIME_INTEGRATION_V7_3_2_REPAIRABLE_ALLOWLIST"
- `core/tasks/scheduler.py:8639` `BLOCKER` `scheduler` `Scheduler._run_simple_task_tick` — Scheduler._run_simple_task_tick = _zero_v733_run_simple_task_tick
- `core/tasks/scheduler.py:8640` `BLOCKER` `scheduler` `Scheduler.CODE_CHAIN_WORKFLOW_STEP_TYPES` — Scheduler.CODE_CHAIN_WORKFLOW_STEP_TYPES = set(getattr(Scheduler, "CODE_CHAIN_WORKFLOW_STEP_TYPES", set())) | _ZERO_V733_CODE_CHAIN_WORKFLOW_STEP_TYPES
- `core/tasks/scheduler.py:8641` `BLOCKER` `scheduler` `Scheduler.SCHEDULER_BUILD` — Scheduler.SCHEDULER_BUILD = "DAG_EXECUTE_SAFETY_LOCK_V8_CODE_CHAIN_RUNTIME_INTEGRATION_V7_3_3_WORKFLOW_TICK_ADVANCEMENT"
- `core/tasks/scheduler.py:9024` `BLOCKER` `scheduler` `Scheduler._sync_runner_result_and_requeue_if_ready` — Scheduler._sync_runner_result_and_requeue_if_ready = _zero_v734_sync_runner_result_and_requeue_if_ready
- `core/tasks/scheduler.py:9025` `BLOCKER` `scheduler` `Scheduler.RETRYING_REPAIR_BRIDGE_VERSION` — Scheduler.RETRYING_REPAIR_BRIDGE_VERSION = "v7.3.4"
- `core/tasks/scheduler.py:9026` `BLOCKER` `scheduler` `Scheduler.SCHEDULER_BUILD` — Scheduler.SCHEDULER_BUILD = "DAG_EXECUTE_SAFETY_LOCK_V8_CODE_CHAIN_RUNTIME_INTEGRATION_V7_3_4_RETRYING_REPAIR_BRIDGE"
- `core/tasks/scheduler.py:9343` `BLOCKER` `scheduler` `Scheduler.approve_review_item` — Scheduler.approve_review_item = _zero_scheduler_approve_review_item
- `core/tasks/scheduler.py:9344` `BLOCKER` `scheduler` `Scheduler.reject_review_item` — Scheduler.reject_review_item = _zero_scheduler_reject_review_item
- `core/tasks/scheduler.py:9381` `BLOCKER` `scheduler` `Scheduler.get_review_queue` — Scheduler.get_review_queue = _zero_scheduler_get_review_queue
- `core/tasks/scheduler.py:9590` `BLOCKER` `scheduler` `Scheduler._is_repairable_failure` — Scheduler._is_repairable_failure = _zero_v7332_is_repairable_failure
- `core/tasks/scheduler.py:9798` `BLOCKER` `scheduler` `Scheduler._is_repairable_failure` — Scheduler._is_repairable_failure = _zero_v7333_is_repairable_failure
- `core/tasks/scheduler.py:9964` `BLOCKER` `scheduler` `Scheduler._is_repairable_failure` — Scheduler._is_repairable_failure = _zero_v7334_is_repairable_failure
- `core/tasks/scheduler.py:10180` `BLOCKER` `scheduler` `Scheduler._is_repairable_failure` — Scheduler._is_repairable_failure = _zero_v7335_is_repairable_failure
- `core/tasks/scheduler.py:10366` `BLOCKER` `scheduler` `Scheduler._is_repairable_failure` — Scheduler._is_repairable_failure = _zero_v7336_is_repairable_failure
- `core/tasks/scheduler.py:10406` `BLOCKER` `scheduler` `Scheduler._try_force_repo_edit_at_create_task` — Scheduler._try_force_repo_edit_at_create_task = _zero_v7337_scheduler_try_force_repo_edit_at_create_task
- `core/tasks/scheduler.py:10407` `BLOCKER` `scheduler` `Scheduler._create_task_record` — Scheduler._create_task_record = _zero_v7337_scheduler_create_task_record
- `core/tasks/scheduler.py:11325` `COMPATIBILITY_BRIDGE` `scheduler` `builtins._zero_operator_completion_registry_v13` — setattr(builtins, "_zero_operator_completion_registry_v13", registry)
- `core/tasks/scheduler.py:11349` `COMPATIBILITY_BRIDGE` `scheduler` `builtins._zero_operator_completion_registry_v13` — setattr(builtins, "_zero_operator_completion_registry_v13", registry)
- `core/tasks/scheduler.py:11359` `COMPATIBILITY_BRIDGE` `scheduler` `builtins._zero_operator_failure_registry_v14` — setattr(builtins, "_zero_operator_failure_registry_v14", failed)
- `core/tasks/scheduler.py:11393` `COMPATIBILITY_BRIDGE` `scheduler` `builtins._zero_operator_failure_registry_v14` — setattr(builtins, "_zero_operator_failure_registry_v14", failed)
- `core/tasks/scheduler.py:11427` `COMPATIBILITY_BRIDGE` `scheduler` `builtins._zero_operator_failure_registry_v14` — setattr(builtins, "_zero_operator_failure_registry_v14", failures)
- `core/tasks/scheduler_core/code_chain_tick_replay_bridge.py:44` `COMPATIBILITY_BRIDGE` `task_runner` `scheduler.task_runner` — scheduler.task_runner = runner
- `core/tasks/scheduler_core/runtime_overlay_helpers.py:227` `BLOCKER` `scheduler` `Scheduler._attach_autonomous_repair_chain_summary` — Scheduler._attach_autonomous_repair_chain_summary = attach_autonomous_repair_chain_summary

## Verification

### PASS: active ZERO_PATCH identifier scan

Active residue count: 0

### PASS: `C:\Users\heero\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall tools core tests`

```text
Listing 'tools'...
Compiling 'tools\\runtime_replacement_inventory_stage11.py'...
Listing 'core'...
Listing 'core\\_archive_candidate'...
Listing 'core\\adaptive'...
Listing 'core\\agent'...
Listing 'core\\artifacts'...
Listing 'core\\audit'...
Listing 'core\\capabilities'...
Listing 'core\\control'...
Listing 'core\\display'...
Listing 'core\\engineering'...
Listing 'core\\events'...
Listing 'core\\evidence'...
Listing 'core\\goals'...
Listing 'core\\memory'...
Listing 'core\\operator'...
Listing 'core\\persona'...
Listing 'core\\planning'...
Listing 'core\\policy'...
Listing 'core\\program'...
Listing 'core\\repo_sandbox'...
Listing 'core\\reports'...
Listing 'core\\runtime'...
Listing 'core\\runtime\\snapshot_loader'...
Listing 'core\\session'...
Listing 'core\\system'...
Listing 'core\\tasks'...
Listing 'core\\tasks\\scheduler_core'...
Listing 'core\\tools'...
Listing 'core\\tools\\_archive_candidate'...
Listing 'core\\verification'...
Listing 'core\\watch'...
Listing 'core\\worker'...
Listing 'core\\world'...
Listing 'tests'...
Listing 'tests\\runtime_contracts'...
Listing 'tests\\task'...
Listing 'tests\\validation'...
```

### PASS: `C:\Users\heero\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest -q tests/runtime_contracts`

```text
..................................................................       [100%]
66 passed in 0.19s
```

### PASS: `C:\Users\heero\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest -q tests/test_runtime_evidence_freeze.py`

```text
..........                                                               [100%]
10 passed in 0.30s
```

### PASS: `C:\Users\heero\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest -q tests/test_runtime_execution_ownership_migration_contract.py`

```text
.....                                                                    [100%]
5 passed in 5.22s
```

### PASS: `C:\Users\heero\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest -q tests/test_runtime_mainline_freeze_contract.py`

```text
....                                                                     [100%]
4 passed in 0.78s
```

### PASS: `C:\Users\heero\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest -q tests/test_runtime_mode_propagation.py`

```text
....                                                                     [100%]
4 passed in 4.86s
```

### PASS: `C:\Users\heero\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest -q tests/test_runner_scheduler_boundary_survival.py`

```text
...                                                                      [100%]
3 passed in 3.12s
```

## Outputs

- `docs/architecture/runtime_native_ownership/runtime_replacement_inventory.json`
- `docs/architecture/runtime_native_ownership/runtime_replacement_summary.json`
- `docs/architecture/runtime_native_ownership/runtime_replacement_report.md`
