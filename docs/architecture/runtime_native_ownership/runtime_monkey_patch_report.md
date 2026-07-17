# Runtime Monkey Patch Elimination Audit - Stage 9

Inventory-only audit for remaining runtime monkey-patch style residue after Native Ownership Stage 8.
This script does not modify runtime behavior.

## Summary

- monkey patch items: 156
- ZERO_PATCH residue: 0
- verification passed: True

## Counts by kind

- `setattr_runtime_injection`: 120
- `class_method_assignment`: 36

## Counts by owner domain

- `unknown`: 80
- `scheduler`: 61
- `runtime_authority`: 7
- `task_runner`: 5
- `planner`: 3

## Items

- `core\agent\agent_loop.py:144` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — setattr(runtime_obj, "operator_bridge", operator_bridge)
- `core\runtime\aer_runtime_integration.py:254` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.runtime_dispatcher = runtime_dispatcher
- `core\runtime\controlled_mutation_sandbox_executor.py:92` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self._patch_identity = copy.deepcopy(patch_identity)
- `core\runtime\controlled_mutation_sandbox_plan.py:31` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self._patch_identity = copy.deepcopy(patch_identity)
- `core\runtime\controlled_mutation_sandbox_plan.py:69` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self._patch_identity = copy.deepcopy(patch_identity)
- `core\runtime\governed_mutation_runtime.py:426` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.patch_plan = create_patch_plan(
- `core\runtime\governed_mutation_runtime.py:462` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.apply_result = apply_patch(
- `core\runtime\governed_mutation_runtime.py:514` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.verification = verify_patch_plan(
- `core\runtime\operator_session_bootstrap.py:144` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — setattr(task, "operator_session_id", resolved)
- `core\runtime\operator_session_bootstrap.py:151` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — setattr(task, "metadata", current_metadata)
- `core\runtime\planner_runtime_dispatch.py:323` `class_method_assignment` `planner` `manual_review_or_promote_to_native_owner` — self.root = self.repo_root / "workspace" / "planner_runtime_dispatch"
- `core\runtime\planner_runtime_dispatch.py:324` `class_method_assignment` `planner` `manual_review_or_promote_to_native_owner` — self.dispatch_log_path = self.root / "dispatch_log.json"
- `core\runtime\runtime_execution_transaction.py:57` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.dispatcher = dispatcher if dispatcher is not None else RuntimeCapabilityDispatcher()
- `core\runtime\runtime_native_agent_loop.py:337` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self._runtime_dispatcher_adapter = None
- `core\runtime\runtime_native_agent_loop.py:339` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self._runtime_dispatcher_adapter = _RuntimeNativeAgentLoopDispatcherAdapter()
- `core\runtime\runtime_native_agent_loop.py:340` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — setattr(self.aer_integration, "runtime_dispatcher", self._runtime_dispatcher_adapter)
- `core\runtime\runtime_native_agent_loop.py:344` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self._runtime_dispatcher_adapter = dispatcher
- `core\runtime\runtime_native_autonomous_repair_chain.py:181` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.patch_pipeline = patch_pipeline
- `core\runtime\runtime_native_code_mutation_loop.py:222` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.dispatch = dispatch
- `core\runtime\runtime_native_engineering_session.py:188` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.dispatch = dispatch
- `core\runtime\runtime_native_execution_dispatch.py:579` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self._dispatches = {}
- `core\runtime\runtime_native_git_patch_pipeline.py:188` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.storage_path = Path(storage_path) if storage_path is not None else self.workspace_root / "workspace" / "runtime_native_git_patch_pipeline.json"
- `core\runtime\runtime_native_multisession_coordination.py:297` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.dispatch = dispatch
- `core\runtime\task_runner.py:6022` `setattr_runtime_injection` `task_runner` `manual_review_or_promote_to_native_owner` — setattr(builtins, '_zero_operator_failure_registry_v14', failures)
- `core\runtime\work_package_operator.py:49` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.dispatcher = dispatcher or RuntimeDispatcher(
- `core\runtime\work_package_operator.py:56` `class_method_assignment` `planner` `manual_review_or_promote_to_native_owner` — self.dispatcher.planner_bridge = self.planner_bridge
- `core\runtime\work_package_operator.py:65` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.dispatcher.llm_client = llm_client
- `core\task_manager.py:511` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — setattr(task, key, copy.deepcopy(runtime_state[key]))
- `core\tasks\engineering_goal_loop.py:146` `class_method_assignment` `unknown` `manual_review_or_promote_to_native_owner` — self.goal_loop_dispatcher = goal_loop_dispatcher or GoalLoopDispatcher(
- `core\tasks\scheduler.py:424` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — self.dispatcher = TaskDispatcher(
- `core\tasks\scheduler.py:7668` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — Scheduler._resolve_guard_target_path = _scheduler_path_compat_resolve_guard_target_path
- `core\tasks\scheduler.py:7782` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — Scheduler._handle_dispatch_result = _scheduler_dispatch_compat_handle_dispatch_result
- `core\tasks\scheduler.py:7783` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — Scheduler._handle_missing_repo_task = _scheduler_dispatch_compat_handle_missing_repo_task
- `core\tasks\scheduler.py:7784` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — Scheduler._handle_run_one_step_exception = _scheduler_dispatch_compat_handle_run_one_step_exception
- `core\tasks\scheduler.py:7785` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — Scheduler._finalize_dispatched_task = _scheduler_dispatch_compat_finalize_dispatched_task
- `core\tasks\scheduler.py:7786` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — Scheduler._extract_effective_status_and_answer = _scheduler_repo_state_compat_extract_effective_status_and_answer
- `core\tasks\scheduler.py:7787` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — Scheduler._mark_repo_task_finished = _scheduler_repo_state_compat_mark_repo_task_finished
- `core\tasks\scheduler.py:7788` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — Scheduler._mark_repo_task_failed = _scheduler_repo_state_compat_mark_repo_task_failed
- `core\tasks\scheduler.py:7789` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — Scheduler._mark_repo_task_queued = _scheduler_repo_state_compat_mark_repo_task_queued
- `core\tasks\scheduler.py:11325` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — setattr(builtins, "_zero_operator_completion_registry_v13", registry)
- `core\tasks\scheduler.py:11349` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — setattr(builtins, "_zero_operator_completion_registry_v13", registry)
- `core\tasks\scheduler.py:11359` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — setattr(builtins, "_zero_operator_failure_registry_v14", failed)
- `core\tasks\scheduler.py:11393` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — setattr(builtins, "_zero_operator_failure_registry_v14", failed)
- `core\tasks\scheduler.py:11427` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — setattr(builtins, "_zero_operator_failure_registry_v14", failures)
- `tests\conftest.py:41` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — setattr(app, "print_json", _legacy_print_json)
- `tests\test_aer_governed_code_chain_landing_contract.py:179` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_aer_legacy_migration_closure.py:108` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "submit_work_package", lambda *_args, **_kwargs: {"ok": True})
- `tests\test_aer_provenance_subject_binding_seal.py:35` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(evidence_validator_module, "_VALIDATED_EVIDENCE", {id(evidence): evidence}, raising=False)
- `tests\test_aer_provenance_subject_binding_seal.py:39` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_aer_terminal_authority_lineage_seal.py:94` `setattr_runtime_injection` `runtime_authority` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(lifecycle_module, "_write_json", lambda *_args: None)
- `tests\test_aer_terminal_authority_lineage_seal.py:100` `setattr_runtime_injection` `runtime_authority` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(lifecycle_module, "_write_json", lambda *_args: None)
- `tests\test_aer_terminal_authority_lineage_seal.py:118` `setattr_runtime_injection` `runtime_authority` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(lifecycle_module, "_write_json", lambda *_args: None)
- `tests\test_aer_terminal_authority_lineage_seal.py:130` `setattr_runtime_injection` `runtime_authority` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_aer_terminal_authority_lineage_seal.py:140` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "submit_work_package", lambda *_args, **_kwargs: {"ok": True, "package_id": "package-a"})
- `tests\test_agent_loop_engineering_goal_route.py:34` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(EngineeringProgramCycle, "run_until_idle", fake_run_until_idle)
- `tests\test_agent_loop_engineering_goal_route.py:35` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(EngineeringGoalLoop, "run_until_terminal", fail_goal_loop)
- `tests\test_agent_loop_engineering_goal_route.py:89` `setattr_runtime_injection` `task_runner` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.tasks.engineering_task_runner.run_engineering_task", fake_run_engineering_task)
- `tests\test_agent_loop_engineering_task_runner.py:207` `setattr_runtime_injection` `task_runner` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.tasks.engineering_task_runner.run_engineering_task", fake_run_engineering_task)
- `tests\test_agent_loop_engineering_task_runner.py:279` `setattr_runtime_injection` `task_runner` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.tasks.engineering_task_runner.run_engineering_task", fake_run_engineering_task)
- `tests\test_agentloop_createtask_mutation_bridge_contract.py:22` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(agent_loop_module, "run_repo_edit_decision", forbidden_repo_edit)
- `tests\test_agentloop_createtask_mutation_bridge_contract.py:49` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "run_repo_edit_decision", forbidden_repo_edit)
- `tests\test_engineering_portfolio_auto_cycle.py:46` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(portfolio_cli, "_portfolio_cycle", lambda repo_root: fake_cycle)
- `tests\test_engineering_portfolio_auto_cycle.py:64` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(portfolio_cli, "_portfolio_cycle", lambda repo_root: fake_cycle)
- `tests\test_engineering_program_auto_cycle.py:41` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(program_cli, "_program_cycle", lambda repo_root: fake_cycle)
- `tests\test_engineering_program_auto_cycle.py:59` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(program_cli, "_program_cycle", lambda repo_root: fake_cycle)
- `tests\test_engineering_program_tree_summary.py:129` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(program_cli, "_program_observability", lambda repo_root: fake)
- `tests\test_engineering_report_usability_contract.py:128` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_goal_cli.py:114` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(goal_cli, "EngineeringGoalScheduler", lambda: spy)
- `tests\test_goal_cli.py:139` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(goal_cli, "EngineeringGoalScheduler", lambda: spy)
- `tests\test_llm_general_generation_contract.py:23` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(llm_client, "requests", Requests())
- `tests\test_repair_chain_runtime.py:1886` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.tasks.scheduler.time.time", lambda: 1_700_000_000.0)
- `tests\test_runtime_dispatcher_status_authority_seal.py:89` `setattr_runtime_injection` `runtime_authority` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(runtime_dispatcher_module, "normalize_runtime_status", canonical_status)
- `tests\test_runtime_phase3_state_evidence_replay.py:128` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(mutation_patch_apply, "apply_patch_plan", partial_apply)
- `tests\test_runtime_replay_execution_bridge.py:2549` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", fake_run)
- `tests\test_runtime_replay_execution_bridge.py:2578` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", fake_run)
- `tests\test_runtime_replay_execution_bridge.py:2620` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:2697` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:2718` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:2740` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", fake_run)
- `tests\test_runtime_replay_execution_bridge.py:2914` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("builtins.open", blocked_open)
- `tests\test_runtime_replay_execution_bridge.py:2915` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(pathlib.Path, "write_text", blocked_write_text)
- `tests\test_runtime_replay_execution_bridge.py:2933` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:2967` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
- `tests\test_runtime_replay_execution_bridge.py:3044` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3057` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", timeout_run)
- `tests\test_runtime_replay_execution_bridge.py:3079` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
- `tests\test_runtime_replay_execution_bridge.py:3101` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3124` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("builtins.open", blocked_open)
- `tests\test_runtime_replay_execution_bridge.py:3125` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(pathlib.Path, "write_text", blocked_write_text)
- `tests\test_runtime_replay_execution_bridge.py:3126` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.json.dump", blocked_json_dump)
- `tests\test_runtime_replay_execution_bridge.py:3149` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", fake_run)
- `tests\test_runtime_replay_execution_bridge.py:3172` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3196` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3222` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3249` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3281` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
- `tests\test_runtime_replay_execution_bridge.py:3312` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
- `tests\test_runtime_replay_execution_bridge.py:3373` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3395` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("builtins.open", blocked_open)
- `tests\test_runtime_replay_execution_bridge.py:3396` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(pathlib.Path, "write_text", blocked_write_text)
- `tests\test_runtime_replay_execution_bridge.py:3397` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.json.dump", blocked_json_dump)
- `tests\test_runtime_replay_execution_bridge.py:3416` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3454` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
- `tests\test_runtime_replay_execution_bridge.py:3485` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3498` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", timeout_run)
- `tests\test_runtime_replay_execution_bridge.py:3536` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3569` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: OkCompleted())
- `tests\test_runtime_replay_execution_bridge.py:3581` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
- `tests\test_runtime_replay_execution_bridge.py:3628` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
- `tests\test_runtime_replay_execution_bridge.py:3652` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("builtins.open", blocked_open)
- `tests\test_runtime_replay_execution_bridge.py:3653` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(pathlib.Path, "write_text", blocked_write_text)
- `tests\test_runtime_replay_execution_bridge.py:3654` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr("core.runtime.task_runtime.json.dump", blocked_json_dump)
- `tests\test_scheduler_dispatch_result_helpers.py:52` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — self.dispatcher = RecordingDispatcher(self.calls)
- `tests\test_scheduler_execution_gateway_basic_step_integration.py:19` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_execution_gateway_basic_step_integration.py:33` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_simple_basic_step", fake_basic_step)
- `tests\test_scheduler_execution_gateway_basic_step_integration.py:34` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_llm_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_basic_step_integration.py:35` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_command_like_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_basic_step_integration.py:63` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_execution_gateway_basic_step_integration.py:75` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_simple_basic_step", lambda **kwargs: dict(legacy_result))
- `tests\test_scheduler_execution_gateway_basic_step_integration.py:76` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "run_scheduler_step_execution_gateway", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("gateway failed")))
- `tests\test_scheduler_execution_gateway_basic_step_integration.py:77` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_llm_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_basic_step_integration.py:78` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_command_like_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_command_like_integration.py:17` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_execution_gateway_command_like_integration.py:23` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_simple_basic_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_command_like_integration.py:24` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_llm_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_command_like_integration.py:34` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_command_like_step", fake_command_like_step)
- `tests\test_scheduler_execution_gateway_command_like_integration.py:60` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_execution_gateway_command_like_integration.py:66` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_simple_basic_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_command_like_integration.py:67` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_llm_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_command_like_integration.py:75` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_command_like_step", lambda **kwargs: dict(legacy_result))
- `tests\test_scheduler_execution_gateway_command_like_integration.py:76` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_execution_gateway_llm_step_integration.py:17` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_execution_gateway_llm_step_integration.py:23` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_simple_basic_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_llm_step_integration.py:33` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_llm_step", fake_llm_step)
- `tests\test_scheduler_execution_gateway_llm_step_integration.py:34` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_command_like_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_llm_step_integration.py:60` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_execution_gateway_llm_step_integration.py:66` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_simple_basic_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_llm_step_integration.py:74` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_llm_step", lambda **kwargs: dict(legacy_result))
- `tests\test_scheduler_execution_gateway_llm_step_integration.py:75` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "execute_command_like_step", lambda **kwargs: None)
- `tests\test_scheduler_execution_gateway_llm_step_integration.py:76` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_runtime_tail_regression.py:45` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_runtime_tail_regression.py:51` `class_method_assignment` `scheduler` `manual_review_or_promote_to_native_owner` — scheduler.dispatcher = EmptyDispatcher()
- `tests\test_scheduler_runtime_tail_regression.py:132` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "_ZERO_V726_ORIGINAL_CREATE_TASK", failing_create_task)
- `tests\test_scheduler_runtime_tail_regression.py:167` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_runtime_tail_regression.py:208` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(scheduler_module, "_ZERO_V726_ORIGINAL_CREATE_TASK", create_after_cleanup)
- `tests\test_scheduler_runtime_tail_regression.py:278` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_runtime_tail_regression.py:318` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_runtime_tail_regression.py:435` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_runtime_tail_regression.py:485` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_runtime_tail_regression.py:568` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_scheduler_runtime_tail_regression.py:574` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(
- `tests\test_session_identity_authority_seal.py:89` `setattr_runtime_injection` `runtime_authority` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(persistent_orchestrator_module, "PersistentEngineeringSession", EngineeringSession)
- `tests\test_session_identity_authority_seal.py:111` `setattr_runtime_injection` `runtime_authority` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(persistent_orchestrator_module, "PersistentEngineeringSession", EngineeringSession)
- `tests\test_verification_tiers.py:109` `setattr_runtime_injection` `unknown` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(verification_cli, "run_verification_cli", fake_cli)
- `tests\test_work_package_adaptive_runtime_feedback.py:161` `class_method_assignment` `task_runner` `manual_review_or_promote_to_native_owner` — operator.dispatcher.task_runner = _AlwaysFailRunner()
- `tests\test_work_package_scheduler.py:130` `setattr_runtime_injection` `scheduler` `manual_review_or_promote_to_native_owner` — monkeypatch.setattr(

## Verification

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m compileall tests/runtime_contracts`
```text
Listing 'tests/runtime_contracts'...
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/runtime_contracts`
```text
..................................................................       [100%]
66 passed in 0.28s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_evidence_freeze.py`
```text
..........                                                               [100%]
10 passed in 0.35s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_execution_ownership_migration_contract.py`
```text
.....                                                                    [100%]
5 passed in 4.73s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mainline_freeze_contract.py`
```text
....                                                                     [100%]
4 passed in 0.75s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mode_propagation.py`
```text
....                                                                     [100%]
4 passed in 4.61s
```

### PASS: `C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runner_scheduler_boundary_survival.py`
```text
...                                                                      [100%]
3 passed in 3.15s
```
