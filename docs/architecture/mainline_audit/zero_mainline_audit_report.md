# ZERO Mainline Audit Report

- Generated at: `2026-06-24T04:42:15.205705+00:00`
- Repo root: `E:\zero_ai`
- Scanned files: `1588`
- Scanned lines: `304845`

## Summary

- Total findings: `5911`
- Severity: `{"high": 110, "info": 2056, "low": 982, "medium": 2763}`
- Category: `{"authority_bypass": 744, "dispatcher_bypass": 23, "evidence_gap": 18, "identity_lineage_gap": 574, "legacy_route": 2130, "runtime_status_alias": 2422}`

## Critical / High Findings

| Severity | Category | File | Line | Finding |
|---|---|---:|---:|---|
| high | authority_bypass | `cli/goal_cli.py` | 113 | direct_file_write: with path.open("w", encoding="utf-8") as handle: |
| high | authority_bypass | `cli/goal_cli.py` | 119 | direct_file_write: with path.open("r", encoding="utf-8") as handle: |
| high | authority_bypass | `cli/runtime_cli.py` | 38 | direct_file_write: with path.open("r", encoding="utf-8") as f: |
| high | authority_bypass | `cli/runtime_cli.py` | 47 | direct_file_write: with path.open("w", encoding="utf-8") as f: |
| high | authority_bypass | `cli/task_cli.py` | 580 | direct_file_write: target.write_text('print("controlled source mutation target")\n', encoding="utf-8") |
| high | authority_bypass | `cli/task_cli.py` | 627 | direct_file_write: target.write_text('print("controlled mutation transaction target")\n', encoding="utf-8") |
| high | authority_bypass | `cli/task_cli.py` | 684 | direct_file_write: target.write_text(f'print("engineering batch target {index}")\n', encoding="utf-8") |
| high | authority_bypass | `cli/task_cli.py` | 741 | direct_file_write: target.write_text(f'print("runtime plan target {index}")\n', encoding="utf-8") |
| high | authority_bypass | `cli/task_cli.py` | 818 | direct_file_write: target.write_text(f'print("runtime session target {group_index}-{target_index}")\n', encoding="utf-8") |
| high | authority_bypass | `cli/verification_cli.py` | 32 | subprocess_or_os_system: completed = subprocess.run( |
| high | authority_bypass | `core/_archive_candidate/flask_manager.py` | 33 | direct_file_write: APP_FILE.write_text(text, encoding="utf-8") |
| high | authority_bypass | `core/_archive_candidate/flask_manager.py` | 78 | direct_file_write: PID_FILE.write_text(str(pid), encoding="utf-8") |
| high | authority_bypass | `core/_archive_candidate/flask_manager.py` | 421 | direct_file_write: APP_FILE.write_text(template, encoding="utf-8") |
| high | legacy_route | `core/agent/agent_loop.py` | 144 | monkey_patch_reference: setattr(runtime_obj, "operator_bridge", operator_bridge) |
| high | authority_bypass | `core/agent/code_chain_repair_evidence.py` | 38 | direct_file_write: evidence_path.write_text( |
| high | authority_bypass | `core/agent/document_flow_trace_writer.py` | 62 | raw_open_write_mode: with open(trace_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/artifacts/registry.py` | 13 | direct_file_write: with path.open("r", encoding="utf-8") as f: |
| high | authority_bypass | `core/artifacts/registry.py` | 21 | direct_file_write: with path.open("w", encoding="utf-8") as f: |
| high | authority_bypass | `core/artifacts/writers.py` | 11 | direct_file_write: path.write_text(text, encoding="utf-8") |
| high | authority_bypass | `core/audit/review_audit.py` | 59 | direct_file_write: with self.path.open("a", encoding="utf-8") as f: |
| high | authority_bypass | `core/audit/review_execution_link.py` | 68 | direct_file_write: with self.path.open("a", encoding="utf-8") as f: |
| high | authority_bypass | `core/audit/task_audit.py` | 107 | raw_open_write_mode: with open(path, "a", encoding="utf-8") as f: |
| high | authority_bypass | `core/capabilities/demo_flows.py` | 163 | direct_file_write: input_path.write_text( |
| high | authority_bypass | `core/capabilities/demo_flows.py` | 178 | direct_file_write: input_path.write_text( |
| high | authority_bypass | `core/capabilities/demo_flows.py` | 292 | direct_file_write: input_path.write_text( |
| high | authority_bypass | `core/capabilities/document_flow_orchestrator.py` | 134 | direct_file_write: path.write_text(DEFAULT_INPUT_TEXT, encoding="utf-8") |
| high | authority_bypass | `core/capabilities/full_build_flow.py` | 181 | direct_file_write: input_path.write_text( |
| high | authority_bypass | `core/capabilities/full_build_flow.py` | 211 | direct_file_write: numbers_input_path.write_text("10\n20\n30\n40\n", encoding="utf-8") |
| high | authority_bypass | `core/capabilities/full_build_flow.py` | 312 | direct_file_write: path.write_text(stabilized, encoding="utf-8") |
| high | authority_bypass | `core/display/ui_bridge.py` | 308 | direct_file_write: _ui_persistence().write_text( |
| high | authority_bypass | `core/events/event_runner.py` | 95 | direct_file_write: self.persistence.write_text( |
| high | authority_bypass | `core/evidence/evidence_repository.py` | 50 | direct_file_write: with self.storage_path.open("a", encoding="utf-8") as stream: |
| high | authority_bypass | `core/evidence/evidence_repository.py` | 142 | direct_file_write: with self.storage_path.open("r", encoding="utf-8") as stream: |
| high | authority_bypass | `core/goals/goal_repository.py` | 215 | direct_file_write: with self.storage_path.open("a", encoding="utf-8") as stream: |
| high | authority_bypass | `core/goals/goal_repository.py` | 223 | direct_file_write: with self.storage_path.open("r", encoding="utf-8") as stream: |
| high | authority_bypass | `core/memory/memory_engine.py` | 51 | raw_open_write_mode: with open(self.memory_file, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/memory/memory_manager.py` | 50 | raw_open_write_mode: with open(self.lesson_file, "a", encoding="utf-8") as f: |
| high | authority_bypass | `core/memory/memory_repository.py` | 33 | direct_file_write: with self.storage_path.open("a", encoding="utf-8") as stream: |
| high | authority_bypass | `core/memory/memory_repository.py` | 84 | direct_file_write: with self.storage_path.open("r", encoding="utf-8") as stream: |
| high | authority_bypass | `core/memory/project_memory.py` | 64 | raw_open_write_mode: with open(self.project_memory_file, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/memory/reflection_manager.py` | 231 | raw_open_write_mode: with open(file_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/memory/task_memory.py` | 209 | raw_open_write_mode: with open(self.file_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/memory/task_memory.py` | 229 | raw_open_write_mode: with open(self.file_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/memory/task_summary.py` | 54 | raw_open_write_mode: with open(summary_file, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/memory/work_package_memory.py` | 211 | direct_file_write: path.write_text( |
| high | authority_bypass | `core/persona/persona_agent_orchestrator.py` | 144 | direct_file_write: input_path.write_text(DEFAULT_INPUT_TEXT, encoding="utf-8") |
| high | authority_bypass | `core/persona/runtime_bridge.py` | 477 | direct_file_write: input_path.write_text("Persona runtime demo input.\n", encoding="utf-8") |
| high | authority_bypass | `core/planning/planner_contract_trace.py` | 97 | direct_file_write: with path.open("a", encoding="utf-8") as f: |
| high | authority_bypass | `core/planning/task_replanner.py` | 1036 | raw_open_write_mode: with open(file_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/repo_sandbox/controlled_edit.py` | 76 | direct_file_write: self.sandbox.write_text(relative_path, updated) |
| high | authority_bypass | `core/repo_sandbox/controlled_edit.py` | 81 | direct_file_write: self.sandbox.write_text(relative_path, new_content) |
| high | authority_bypass | `core/repo_sandbox/review.py` | 66 | direct_file_write: path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8") |
| high | authority_bypass | `core/repo_sandbox/review.py` | 324 | direct_file_write: target.write_text(sandbox_file.read_text(encoding="utf-8"), encoding="utf-8") |
| high | authority_bypass | `core/repo_sandbox/review_flow.py` | 267 | direct_file_write: sandbox_path.write_text(modified, encoding="utf-8") |
| high | authority_bypass | `core/repo_sandbox/sandbox.py` | 104 | direct_file_write: sandbox_file.sandbox_path.write_text(content, encoding="utf-8") |
| high | authority_bypass | `core/repo_sandbox/tool.py` | 353 | direct_file_write: workspace_path.write_text(str(request.new_content or ""), encoding="utf-8") |
| high | authority_bypass | `core/repo_sandbox/tool.py` | 456 | direct_file_write: workspace_path.write_text(edited_content, encoding="utf-8") |
| high | legacy_route | `core/task_manager.py` | 511 | monkey_patch_reference: setattr(task, key, copy.deepcopy(runtime_state[key])) |
| high | authority_bypass | `core/task_manager.py` | 551 | raw_open_write_mode: with open(path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/engineering_artifact_repository.py` | 230 | direct_file_write: self.storage_path.write_text( |
| high | authority_bypass | `core/tasks/engineering_evidence_repository.py` | 241 | direct_file_write: self.storage_path.write_text( |
| high | authority_bypass | `core/tasks/engineering_goal_lifecycle.py` | 77 | direct_file_write: path.write_text( |
| high | authority_bypass | `core/tasks/engineering_goal_repository.py` | 363 | direct_file_write: self.storage_path.write_text( |
| high | authority_bypass | `core/tasks/engineering_issue_reporter.py` | 175 | direct_file_write: self.storage_path.write_text( |
| high | authority_bypass | `core/tasks/engineering_memory_store.py` | 104 | direct_file_write: self.path.write_text( |
| high | authority_bypass | `core/tasks/engineering_portfolio_repository.py` | 274 | direct_file_write: self.storage_path.write_text( |
| high | authority_bypass | `core/tasks/engineering_program_repository.py` | 249 | direct_file_write: self.storage_path.write_text( |
| high | authority_bypass | `core/tasks/engineering_task_runner.py` | 101 | direct_file_write: path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8") |
| high | authority_bypass | `core/tasks/execution_contract_trace.py` | 83 | direct_file_write: with path.open("a", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/runtime_repair_apply_transaction.py` | 3538 | direct_file_write: target_path.write_text(str(content), encoding="utf-8") |
| high | authority_bypass | `core/tasks/runtime_repair_apply_transaction.py` | 3675 | direct_file_write: target_path.write_text(str(content), encoding="utf-8") |
| high | authority_bypass | `core/tasks/runtime_repair_apply_transaction.py` | 3681 | direct_file_write: target_path.write_text(_minimal_patch_result(patch_text), encoding="utf-8") |
| high | authority_bypass | `core/tasks/scheduler.py` | 1790 | raw_open_write_mode: with open(trace_path, "a", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/scheduler.py` | 3484 | raw_open_write_mode: with open(path, "w", encoding="utf-8") as fh: |
| high | authority_bypass | `core/tasks/scheduler.py` | 5872 | raw_open_write_mode: with open(runtime_state_file, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/scheduler.py` | 6012 | raw_open_write_mode: with open(snapshot_file, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/scheduler.py` | 6029 | raw_open_write_mode: with open(result_file, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/scheduler.py` | 6038 | raw_open_write_mode: with open(execution_log_file, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/scheduler.py` | 6738 | raw_open_write_mode: with open(path, "w", encoding="utf-8", newline="") as f: |
| high | authority_bypass | `core/tasks/scheduler.py` | 8939 | raw_open_write_mode: with open(path, "w", encoding="utf-8") as f: |
| high | legacy_route | `core/tasks/scheduler.py` | 11325 | monkey_patch_reference: setattr(builtins, "_zero_operator_completion_registry_v13", registry) |
| high | legacy_route | `core/tasks/scheduler.py` | 11349 | monkey_patch_reference: setattr(builtins, "_zero_operator_completion_registry_v13", registry) |
| high | legacy_route | `core/tasks/scheduler.py` | 11359 | monkey_patch_reference: setattr(builtins, "_zero_operator_failure_registry_v14", failed) |
| high | legacy_route | `core/tasks/scheduler.py` | 11393 | monkey_patch_reference: setattr(builtins, "_zero_operator_failure_registry_v14", failed) |
| high | legacy_route | `core/tasks/scheduler.py` | 11427 | monkey_patch_reference: setattr(builtins, "_zero_operator_failure_registry_v14", failures) |
| high | authority_bypass | `core/tasks/scheduler_core/atomic_edit_helpers.py` | 73 | raw_open_write_mode: with open(candidate, "w", encoding="utf-8", newline="") as f: |
| high | authority_bypass | `core/tasks/scheduler_core/atomic_edit_helpers.py` | 80 | raw_open_write_mode: with open(record.path, "w", encoding="utf-8", newline="") as f: |
| high | authority_bypass | `core/tasks/scheduler_core/simple_step_executor_helpers.py` | 283 | raw_open_write_mode: with open(full_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/scheduler_core/simple_step_executor_helpers.py` | 331 | raw_open_write_mode: with open(full_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/scheduler_core/simple_step_executor_helpers.py` | 396 | raw_open_write_mode: with open(full_path, "a", encoding="utf-8", newline="") as f: |
| high | authority_bypass | `core/tasks/simple_step_runner.py` | 103 | raw_open_write_mode: with open(full_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/simple_step_runner.py` | 135 | raw_open_write_mode: with open(full_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/task_index.py` | 27 | direct_file_write: with path.open("r", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/task_intake_evidence.py` | 42 | direct_file_write: evidence_path.write_text( |
| high | authority_bypass | `core/tasks/task_scheduler_loop.py` | 30 | raw_open_write_mode: with open(SCHEDULER_LOG, "a", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/task_storage.py` | 35 | raw_open_write_mode: with open(task_file, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/task_store_lock.py` | 34 | raw_open_write_mode: handle = open(self.lock_path, "a+b") |
| high | authority_bypass | `core/tasks/task_store_lock.py` | 93 | raw_open_write_mode: with os.fdopen(fd, "w", encoding="utf-8") as handle: |
| high | authority_bypass | `core/tasks/task_workspace.py` | 255 | raw_open_write_mode: with open(log_path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/task_workspace.py` | 295 | raw_open_write_mode: with open(path, "w", encoding="utf-8") as f: |
| high | authority_bypass | `core/tasks/work_package_audit_executor.py` | 277 | direct_file_write: report_path.write_text(report, encoding="utf-8") |
| high | authority_bypass | `core/tasks/work_package_intake.py` | 59 | direct_file_write: path.write_text(content, encoding="utf-8") |
| high | authority_bypass | `core/tasks/work_package_intake.py` | 65 | direct_file_write: path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8") |
| high | authority_bypass | `core/tasks/work_package_intake.py` | 678 | direct_file_write: backup.write_text(before_text, encoding="utf-8") |
| high | authority_bypass | `core/tasks/work_package_intake.py` | 681 | direct_file_write: backup.write_text("", encoding="utf-8") |
| high | authority_bypass | `core/tasks/work_package_intake.py` | 684 | direct_file_write: target.write_text(after_content, encoding="utf-8") |
| high | authority_bypass | `core/tasks/work_package_intake.py` | 793 | direct_file_write: target.write_text(before_text, encoding="utf-8") |
| high | authority_bypass | `core/tasks/work_package_intake.py` | 1486 | direct_file_write: target.write_text(content, encoding="utf-8") |
| high | authority_bypass | `core/tasks/work_package_scheduler.py` | 87 | direct_file_write: path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8") |
| high | authority_bypass | `core/world/world_state.py` | 48 | raw_open_write_mode: with open(self.path, "w", encoding="utf-8") as f: |

## Large File Inventory

| File | Lines | Functions | Classes | Max Function Lines |
|---|---:|---:|---:|---:|
| `core/tasks/scheduler.py` | 11432 | 314 | 1 | 297 |
| `core/agent/agent_loop.py` | 8262 | 173 | 1 | 355 |
| `tests/test_runtime_repair_apply_transaction.py` | 3931 | 210 | 0 | 63 |
| `core/tasks/runtime_repair_apply_transaction.py` | 3817 | 161 | 0 | 125 |
| `tests/test_runtime_replay_execution_bridge.py` | 3662 | 205 | 29 | 51 |
| `tests/test_runtime_workflow_session_contract.py` | 3177 | 22 | 0 | 310 |
| `core/planning/planner.py` | 2816 | 99 | 1 | 206 |
| `tests/test_repair_chain_runtime.py` | 2355 | 81 | 5 | 59 |
| `cli/task_cli.py` | 1684 | 63 | 0 | 89 |
| `core/tasks/work_package_intake.py` | 1659 | 0 | 0 | 0 |
| `core/tasks/engineering_task_runner.py` | 1597 | 51 | 0 | 376 |
| `core/persona/runtime_bridge.py` | 1344 | 47 | 4 | 125 |
| `core/system/llm_planner.py` | 1307 | 44 | 1 | 104 |
| `core/tasks/scheduler_core/repo_state_helpers.py` | 1174 | 34 | 0 | 239 |
| `core/planning/task_replanner.py` | 1040 | 32 | 1 | 190 |

## Top Finding Files

| File | Findings |
|---|---:|
| `core/tasks/scheduler.py` | 308 |
| `core/agent/agent_loop.py` | 230 |
| `tests/test_repair_chain_runtime.py` | 124 |
| `core/tasks/scheduler_execution_gateway.py` | 82 |
| `tests/runtime_contracts/test_step_executor_contracts.py` | 74 |
| `tests/test_runtime_replay_execution_bridge.py` | 66 |
| `core/tasks/work_package_intake.py` | 65 |
| `core/tasks/runtime_repair_apply_transaction.py` | 53 |
| `core/memory/reflection_engine.py` | 48 |
| `core/planning/planner.py` | 45 |
| `core/agent/code_chain_controlled_self_edit_bridge.py` | 44 |
| `core/tasks/execution_gateway.py` | 41 |
| `core/persona/runtime_bridge.py` | 40 |
| `tools/archive/runtime_governance_closure/runtime_replacement_inventory_stage11.py` | 37 |
| `core/tools/_archive_candidate/memory_tool.py` | 35 |
| `tests/test_execution_gateway_runtime.py` | 34 |
| `core/_archive_candidate/flask_manager.py` | 33 |
| `tools/archive/runtime_governance_closure/stepexecutor_native_ownership_closure_stage13c.py` | 32 |
| `tools/zero_mainline_audit.py` | 30 |
| `core/memory/task_memory.py` | 29 |
| `core/display/runtime_presenter.py` | 29 |
| `core/system/response_formatter.py` | 29 |
| `core/tasks/execution_gateway_runtime.py` | 29 |
| `tools/archive/runtime_governance_closure/aer_ownership_migration_plan_stage14.py` | 29 |
| `tools/archive/runtime_governance_closure/runtime_monkey_patch_elimination_stage9.py` | 29 |

## Non-Mainline Issue Report

| Severity | Category | File | Line | Finding |
|---|---|---:|---:|---|
| low | runtime_status_alias | `cli/runtime_cli.py` | 225 | legacy_done_status: "done", |
| low | runtime_status_alias | `cli/runtime_cli.py` | 261 | legacy_done_status: "done", |
| low | legacy_route | `cli/runtime_cli.py` | 299 | deprecated_reference: "legacy_app_booted": False, |
| low | legacy_route | `cli/runtime_cli.py` | 335 | deprecated_reference: "legacy_app_booted": False, |
| low | legacy_route | `cli/runtime_cli.py` | 350 | deprecated_reference: """Build the real Runtime Kernel summary without booting app_legacy.py. |
| low | legacy_route | `cli/runtime_cli.py` | 365 | deprecated_reference: status.setdefault("legacy_app_booted", False) |
| low | legacy_route | `cli/runtime_cli.py` | 373 | deprecated_reference: "legacy_app_booted": False, |
| low | legacy_route | `cli/runtime_cli.py` | 421 | deprecated_reference: "legacy_app_booted": False, |
| low | legacy_route | `cli/runtime_cli.py` | 446 | deprecated_reference: "legacy_app_booted": False, |
| low | legacy_route | `cli/task_cli.py` | 79 | deprecated_reference: "legacy_app_booted": False, |
| low | legacy_route | `cli/task_cli.py` | 91 | deprecated_reference: "legacy_app_booted": False, |
| low | legacy_route | `cli/task_cli.py` | 474 | deprecated_reference: "legacy_app_booted": False, |
| low | legacy_route | `cli/task_cli.py` | 1328 | deprecated_reference: def _has_legacy_scheduler_runnable_tasks(repo_root: Path) -> bool: |
| low | legacy_route | `cli/task_cli.py` | 1329 | deprecated_reference: """Return True when task run should fall through to the full legacy Scheduler. |
| low | legacy_route | `cli/task_cli.py` | 1332 | deprecated_reference: Full runtime tasks created by app_legacy.py/task_repository are persisted in |
| low | legacy_route | `cli/task_cli.py` | 1591 | deprecated_reference: "legacy_app_booted": False, |
| low | legacy_route | `cli/task_cli.py` | 1618 | deprecated_reference: if _has_legacy_scheduler_runnable_tasks(repo_root): |
| low | legacy_route | `cli/verification_cli.py` | 51 | deprecated_reference: legacy_diagnostic_output=command.legacy_diagnostic_output, |
| low | legacy_route | `cli/verification_cli.py` | 66 | deprecated_reference: legacy_diagnostic_output=command.legacy_diagnostic_output, |
| low | legacy_route | `cli/verification_cli.py` | 83 | deprecated_reference: suffix = " legacy_diagnostic_output=true" if item.get("legacy_diagnostic_output") else "" |
| low | legacy_route | `cli/work_package_cli.py` | 42 | deprecated_reference: "scheduler_compatibility_payload": True, |
| low | legacy_route | `cli/work_package_cli.py` | 66 | deprecated_reference: def _print_readable_report(repo_root: str, package_id: str, fallback: dict[str, Any] \| None = None) -> None: |
| low | legacy_route | `cli/work_package_cli.py` | 67 | deprecated_reference: data = _read_memory(repo_root, package_id) or fallback or {} |
| low | legacy_route | `core/_archive_candidate/model_router.py` | 8 | deprecated_reference: "reason": "empty fallback", |
| low | runtime_status_alias | `core/adaptive/adaptive_runtime_resume.py` | 85 | legacy_done_status: if str(result.get("status") or "").lower() not in {"needs_observation", "finished", "completed", "success", "done"}: |
| low | runtime_status_alias | `core/adaptive/adaptive_runtime_resume.py` | 98 | legacy_done_status: if str(observed.get("status") or "").lower() in {"finished", "completed", "success", "done"}: |
| low | legacy_route | `core/adaptive/adaptive_runtime_resume.py` | 179 | deprecated_reference: def _executed_step_index(result: Mapping[str, Any], fallback: int) -> int: |
| low | legacy_route | `core/adaptive/adaptive_runtime_resume.py` | 183 | deprecated_reference: return fallback |
| low | legacy_route | `core/agent/agent_component_invoker.py` | 23 | deprecated_reference: "legacy_adapter": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 355 | deprecated_reference: engineering_task_result.setdefault("legacy_direct_json_engineering_task_runner", True) |
| low | legacy_route | `core/agent/agent_loop.py` | 431 | deprecated_reference: "legacy_direct_json_engineering_task_runner": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 503 | deprecated_reference: "legacy_direct_engineering_task_route": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 519 | deprecated_reference: "legacy_direct_json_engineering_task_runner": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 549 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 608 | deprecated_reference: "legacy_direct_json_engineering_task_runner": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 614 | deprecated_reference: """Handle legacy direct JSON engineering_task payloads. |
| low | legacy_route | `core/agent/agent_loop.py` | 616 | deprecated_reference: Legacy boundary: |
| low | legacy_route | `core/agent/agent_loop.py` | 617 | deprecated_reference: - This route is intentionally labelled legacy. |
| low | legacy_route | `core/agent/agent_loop.py` | 653 | deprecated_reference: "legacy_direct_json_engineering_task_runner": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 688 | deprecated_reference: result["legacy_direct_json_engineering_task_runner"] = bool(1) |
| low | legacy_route | `core/agent/agent_loop.py` | 705 | deprecated_reference: "legacy_direct_json_engineering_task_runner": bool(1), |
| low | legacy_route | `core/agent/agent_loop.py` | 707 | deprecated_reference: "legacy_isolated": True, |
| low | legacy_route | `core/agent/agent_loop.py` | 708 | deprecated_reference: "authority_path": "AgentLoop -> LegacyEngineeringTaskAdmission -> Planner -> WorkPackageIntake", |
| low | legacy_route | `core/agent/agent_loop.py` | 718 | deprecated_reference: "legacy_direct_engineering_task_route": True, |
| low | legacy_route | `core/agent/agent_loop.py` | 732 | deprecated_reference: "planner_mode": "legacy_engineering_task_runner_v1", |
| low | legacy_route | `core/agent/agent_loop.py` | 738 | deprecated_reference: "type": "legacy_engineering_task_runner_delegate", |
| low | legacy_route | `core/agent/agent_loop.py` | 743 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 745 | deprecated_reference: "legacy_isolated": True, |
| low | legacy_route | `core/agent/agent_loop.py` | 760 | deprecated_reference: "type": "legacy_engineering_task_runner_delegate", |
| low | legacy_route | `core/agent/agent_loop.py` | 862 | deprecated_reference: "legacy_engineering_goal_route": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 947 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 1587 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 1711 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 1906 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 2764 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 2909 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 3254 | deprecated_reference: fallback=user_input, |
| low | legacy_route | `core/agent/agent_loop.py` | 4142 | deprecated_reference: fallback: str, |
| low | legacy_route | `core/agent/agent_loop.py` | 4161 | deprecated_reference: return self._extract_final_answer(runner_result, None, fallback) |
| low | legacy_route | `core/agent/agent_loop.py` | 4238 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 4257 | deprecated_reference: meta["fallback_used"] = bool(meta.get("fallback_used", False)) |
| low | legacy_route | `core/agent/agent_loop.py` | 4384 | deprecated_reference: def _execute_l5_or_legacy_tool_plan( |
| low | legacy_route | `core/agent/agent_loop.py` | 4886 | deprecated_reference: single_shot_result["mode"] = "llm_fallback_single_shot" |
| low | legacy_route | `core/agent/agent_loop.py` | 4906 | deprecated_reference: single_shot_result["mode"] = "llm_fallback_single_shot" |
| low | legacy_route | `core/agent/agent_loop.py` | 4917 | deprecated_reference: single_shot_result["mode"] = "llm_fallback_single_shot" |
| low | legacy_route | `core/agent/agent_loop.py` | 5058 | deprecated_reference: execution_result = self._execute_l5_or_legacy_tool_plan( |
| low | legacy_route | `core/agent/agent_loop.py` | 5277 | deprecated_reference: execution_result = self._execute_l5_or_legacy_tool_plan( |
| low | legacy_route | `core/agent/agent_loop.py` | 5304 | deprecated_reference: return self._run_task_mode_legacy_enqueue( |
| low | legacy_route | `core/agent/agent_loop.py` | 5487 | deprecated_reference: def _run_task_mode_legacy_enqueue( |
| low | legacy_route | `core/agent/agent_loop.py` | 6210 | deprecated_reference: def _extract_final_answer(self, execution: Any, plan: Any, fallback: str) -> str: |
| low | legacy_route | `core/agent/agent_loop.py` | 6228 | deprecated_reference: if isinstance(fallback, str) and fallback.strip(): |
| low | legacy_route | `core/agent/agent_loop.py` | 6229 | deprecated_reference: return fallback.strip() |
| low | legacy_route | `core/agent/agent_loop.py` | 6489 | deprecated_reference: "fallback_used": False, |
| low | legacy_route | `core/agent/agent_loop.py` | 8166 | deprecated_reference: failure_reason = "legacy_runtime_dispatcher_migration_required" |
| low | legacy_route | `core/agent/agent_loop.py` | 8212 | deprecated_reference: "legacy_runtime_dispatcher_migration_required": True, |
| low | legacy_route | `core/agent/agent_loop.py` | 8245 | deprecated_reference: fallback_candidate = globals().get("_zero_v826_code_fix_bridge_candidate") |
| low | legacy_route | `core/agent/agent_loop.py` | 8257 | deprecated_reference: fallback_candidate=fallback_candidate if callable(fallback_candidate) else None, |
| low | legacy_route | `core/agent/agent_loop.py` | 8258 | deprecated_reference: fallback_enabled=False, |
| low | evidence_gap | `core/agent/agent_route_policy.py` | 42 | todo_fixme: action_keywords = ["action item", "action items", "待辦事項", "行動項目", "todo", "to-do"] |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 33 | deprecated_reference: fallback_candidate: Callable[[str], bool] \| None = None, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 34 | deprecated_reference: fallback_enabled: bool = True, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 69 | deprecated_reference: fallback_used = False |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 71 | deprecated_reference: if not fallback_enabled or not callable(fallback_candidate) or not bool(fallback_candidate(text)): |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 73 | deprecated_reference: fallback_used = True |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 76 | deprecated_reference: "source": "agent_loop_keyword_fallback", |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 77 | deprecated_reference: "reason": "v1 fallback candidate matched", |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 107 | deprecated_reference: "planner_owned_intent_routing": not fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 108 | deprecated_reference: "fallback_used": fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 115 | deprecated_reference: "planner_owned_intent_routing": not fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 116 | deprecated_reference: "code_chain_v1_fallback_used": fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 155 | deprecated_reference: "planner_owned_intent_routing": not fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 156 | deprecated_reference: "fallback_used": fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 173 | deprecated_reference: "planner_owned_intent_routing": not fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 174 | deprecated_reference: "code_chain_v1_fallback_used": fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 214 | deprecated_reference: "planner_owned_intent_routing": not fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 215 | deprecated_reference: "fallback_used": fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 229 | deprecated_reference: "planner_owned_intent_routing": not fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 230 | deprecated_reference: "code_chain_v1_fallback_used": fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 244 | deprecated_reference: fallback_used=fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 292 | deprecated_reference: fallback_used=fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 346 | deprecated_reference: execution["planner_owned_intent_routing"] = not fallback_used |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 386 | deprecated_reference: "planner_owned_intent_routing": not fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 387 | deprecated_reference: "fallback_used": fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 390 | deprecated_reference: "agent_loop_keyword_detection_is_fallback_only": True, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 406 | deprecated_reference: "planner_owned_intent_routing": not fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 407 | deprecated_reference: "code_chain_v1_fallback_used": fallback_used, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 477 | deprecated_reference: fallback_used: bool, |
| low | legacy_route | `core/agent/code_chain_controlled_self_edit_bridge.py` | 491 | deprecated_reference: "planner_owned_intent_routing": not fallback_used, |
| low | runtime_status_alias | `core/agent/local_observer.py` | 6 | legacy_done_status: TERMINAL_STATUSES = {"finished", "failed", "blocked", "cancelled", "done", "completed", "success"} |
| low | runtime_status_alias | `core/agent/loop_decision.py` | 13 | legacy_done_status: "done", |
| low | runtime_status_alias | `core/agent/loop_decision.py` | 23 | legacy_done_status: SUCCESS_STATUSES = {"finished", "completed", "done", "success"} |
| low | legacy_route | `core/agent/loop_decision.py` | 142 | deprecated_reference: def _legacy_review_blocker_from_sources(*sources: Dict[str, Any]) -> dict[str, Any] \| None: |
| low | legacy_route | `core/agent/loop_decision.py` | 179 | deprecated_reference: legacy_review = _legacy_review_blocker_from_sources(local, result, runtime_state, task_dict) |
| low | legacy_route | `core/agent/loop_decision.py` | 180 | deprecated_reference: if legacy_review: |
| low | legacy_route | `core/agent/loop_decision.py` | 181 | deprecated_reference: blockers = normalize_blockers([legacy_review]) |
| low | evidence_gap | `core/agent/observe.py` | 15 | todo_fixme: # TODO: 之後這裡可以接 camera / file watcher / event |
| low | legacy_route | `core/agent/router_backup.py` | 26 | deprecated_reference: Compatibility surface: |
| low | legacy_route | `core/agent/router_backup.py` | 31 | deprecated_reference: ``source`` is accepted for provenance compatibility with |
| low | legacy_route | `core/artifacts/writers.py` | 166 | deprecated_reference: "- Legacy runtime boot was avoided for this smoke path.\n" |
| low | legacy_route | `core/artifacts/writers.py` | 194 | deprecated_reference: "- Legacy boot avoided for ask/chat/task run/help/runtime/health/replay\n" |
| low | legacy_route | `core/display/runtime_presenter.py` | 48 | deprecated_reference: The legacy summary/detail functions intentionally keep their existing narrative |
| low | runtime_status_alias | `core/display/runtime_presenter.py` | 241 | legacy_done_status: if lowered in {"finished", "completed", "done", "success"}: |
| low | legacy_route | `core/evidence/decision_evidence.py` | 6 | deprecated_reference: DecisionEvidenceRepository name is retained as a compatibility projection/view, |
| low | legacy_route | `core/evidence/decision_evidence.py` | 142 | deprecated_reference: """Compatibility projection backed by EvidenceAuthority. |
| low | legacy_route | `core/evidence/decision_evidence.py` | 145 | deprecated_reference: repository preserves round-trip identity for compatibility callers. |
| low | legacy_route | `core/goals/goal_lineage_contract.py` | 32 | deprecated_reference: INVALID_IDENTITY_VALUES = frozenset({"unknown", "default", "legacy", "runtime", "system"}) |
| low | legacy_route | `core/llm_client.py` | 1 | deprecated_reference: """Compatibility import for the canonical system LLM client.""" |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 41 | deprecated_reference: "read_path": ["TaskMemory record reads", "legacy TaskRepository reads"], |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 43 | deprecated_reference: "lifecycle_authority": "none; legacy TaskRepository status is deprecated local task metadata", |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 49 | deprecated_reference: "deprecated_paths": ["core.task_memory", "TaskRepository lifecycle-like status API"], |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 68 | deprecated_reference: "deprecated_paths": [], |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 88 | deprecated_reference: "deprecated_paths": [], |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 102 | deprecated_reference: "deprecated_paths": [], |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 116 | deprecated_reference: "deprecated_paths": [], |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 133 | deprecated_reference: "deprecated_paths": sorted( |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 134 | deprecated_reference: {path for item in modules for path in item["deprecated_paths"]} |
| low | legacy_route | `core/memory/memory_ownership_contract.py` | 137 | deprecated_reference: "legacy_task_repository_status_is_not_runtime_lifecycle_authority", |
| low | legacy_route | `core/memory/reflection_engine.py` | 108 | deprecated_reference: fallback_issue = ReflectionIssue( |
| low | legacy_route | `core/memory/reflection_engine.py` | 115 | deprecated_reference: fallback_report = ReflectionReport( |
| low | legacy_route | `core/memory/reflection_engine.py` | 120 | deprecated_reference: issues=[fallback_issue], |
| low | legacy_route | `core/memory/reflection_engine.py` | 125 | deprecated_reference: return fallback_report.to_dict() |
| low | runtime_status_alias | `core/memory/reflection_engine.py` | 389 | legacy_done_status: if status in ("success", "completed", "done", "ok"): |
| low | legacy_route | `core/memory/reflection_engine.py` | 713 | deprecated_reference: if any(k in lower for k in ["warn", "warning", "retry", "fallback"]): |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 240 | deprecated_reference: failure_type=self._map_error_type_to_failure_type(error_type, fallback=failure_type), |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 264 | deprecated_reference: failure_type=self._map_error_type_to_failure_type(error_type, fallback="transient_error"), |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 283 | deprecated_reference: failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"), |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 297 | deprecated_reference: failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"), |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 318 | deprecated_reference: failure_type=self._map_error_type_to_failure_type(error_type, fallback="validation_error"), |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 332 | deprecated_reference: failure_type=self._map_error_type_to_failure_type(error_type, fallback="validation_error"), |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 355 | deprecated_reference: failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"), |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 374 | deprecated_reference: failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"), |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 388 | deprecated_reference: failure_type=self._map_error_type_to_failure_type(error_type, fallback="tool_error"), |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 621 | deprecated_reference: def _map_error_type_to_failure_type(self, error_type: str, fallback: str = "tool_error") -> str: |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 636 | deprecated_reference: "unknown_error": fallback or "tool_error", |
| low | legacy_route | `core/memory/step_reflection_engine.py` | 640 | deprecated_reference: return mapping.get(error_type, fallback or "tool_error") |
| low | runtime_status_alias | `core/memory/step_reflection_engine.py` | 727 | legacy_done_status: if status in {"ok", "success", "completed", "done"}: |
| low | runtime_status_alias | `core/memory/task_memory.py` | 87 | legacy_done_status: status: str = "pending"   # pending / running / done / failed / skipped |
| low | runtime_status_alias | `core/memory/task_memory.py` | 475 | legacy_done_status: step.status = "done" |
| low | runtime_status_alias | `core/memory/task_memory.py` | 618 | legacy_done_status: return all(step.status in ("done", "skipped") for step in task.steps) |
| low | legacy_route | `core/operator/codex_operator.py` | 240 | deprecated_reference: return _blocked(current, "legacy_runtime_dispatcher_migration_required") |
| low | legacy_route | `core/operator/verification_runner.py` | 48 | deprecated_reference: stderr="legacy_runtime_dispatcher_migration_required", |
| low | runtime_status_alias | `core/persona/chat_shell.py` | 326 | legacy_done_status: if display.get("runtime_status") == "done": |
| low | runtime_status_alias | `core/persona/chat_shell.py` | 333 | legacy_done_status: last_result="done", |
| low | evidence_gap | `core/persona/persona_agent_orchestrator.py` | 163 | todo_fixme: "todo", |
| low | runtime_status_alias | `core/persona/runtime_bridge.py` | 20 | legacy_done_status: RUNTIME_STATUSES = {"planning", "executing", "blocked", "done", "failed"} |
| low | runtime_status_alias | `core/persona/runtime_bridge.py` | 699 | legacy_done_status: return "done" |
| low | runtime_status_alias | `core/persona/runtime_bridge.py` | 1122 | legacy_done_status: if runtime_status in {"done", "executing"}: |
| low | runtime_status_alias | `core/persona/runtime_bridge.py` | 1252 | legacy_done_status: if status == "done": |
| low | legacy_route | `core/planning/planner.py` | 55 | deprecated_reference: - generic_task -> fallback to generic planner path |
| low | legacy_route | `core/planning/planner.py` | 166 | deprecated_reference: fallback_used=False, |
| low | legacy_route | `core/planning/planner.py` | 195 | deprecated_reference: fallback_used=False, |
| low | legacy_route | `core/planning/planner.py` | 239 | deprecated_reference: fallback_used=False, |
| low | legacy_route | `core/planning/planner.py` | 259 | deprecated_reference: raw_steps, fallback_used = self._plan_steps(text=text, route=route, context=context) |
| low | legacy_route | `core/planning/planner.py` | 274 | deprecated_reference: fallback_used=fallback_used, |
| low | legacy_route | `core/planning/planner.py` | 282 | deprecated_reference: message=f"steps={len(steps)}, intent={intent}, semantic_type={semantic_type}, fallback={fallback_used}", |
| low | legacy_route | `core/planning/planner.py` | 300 | deprecated_reference: fallback_used=False, |
| low | legacy_route | `core/planning/planner.py` | 455 | deprecated_reference: parsed = self._fallback_match_code_chain_diff_v0_task(text=text) |
| low | evidence_gap | `core/planning/planner.py` | 582 | todo_fixme: if any(token in lowered for token in ["action items", "action-items", "action_items", "extract actions", "todo list"]): |
| low | legacy_route | `core/planning/planner.py` | 745 | deprecated_reference: def _fallback_match_code_chain_diff_v0_task(self, text: str) -> Optional[Dict[str, str]]: |
| low | evidence_gap | `core/planning/planner.py` | 1030 | todo_fixme: "todo list", |
| low | evidence_gap | `core/planning/planner.py` | 1100 | todo_fixme: r"(?:write\|create\|save\|output\|produce\|extract)\s+(?:the\s+)?(?:action\s+items\|action-items\|action_items\|todo\s+list\|todos)\s+(?:to\|into\|as)\s+([^\s,;]+)", |
| low | evidence_gap | `core/planning/planner.py` | 1104 | todo_fixme: r"(?:action\s+items\|action-items\|action_items\|todo\s+list\|todos)[^,;]*?\b(?:to\|into\|as)\s+([^\s,;]+)", |
| low | legacy_route | `core/planning/planner.py` | 1395 | deprecated_reference: fallback_used = False |
| low | legacy_route | `core/planning/planner.py` | 1399 | deprecated_reference: sub_steps, clause_fallback_used, last_path = self._plan_single_clause( |
| low | legacy_route | `core/planning/planner.py` | 1405 | deprecated_reference: if clause_fallback_used: |
| low | legacy_route | `core/planning/planner.py` | 1406 | deprecated_reference: fallback_used = True |
| low | legacy_route | `core/planning/planner.py` | 1409 | deprecated_reference: return steps, fallback_used |
| low | evidence_gap | `core/planning/planner.py` | 1478 | todo_fixme: if any(token in lowered for token in ["action items", "action-items", "todo list", "extract actions"]): |
| low | legacy_route | `core/planning/planner.py` | 1710 | deprecated_reference: title="fallback detected", |
| low | legacy_route | `core/planning/planner.py` | 2054 | deprecated_reference: fallback_used: bool, |
| low | legacy_route | `core/planning/planner.py` | 2074 | deprecated_reference: "fallback_used": bool(fallback_used), |
| low | legacy_route | `core/planning/planner.py` | 2088 | deprecated_reference: fallback_task_name = self._infer_task_name(task_dir="", goal="planner_steps") |
| low | legacy_route | `core/planning/planner.py` | 2095 | deprecated_reference: fallback_task_name=fallback_task_name, |
| low | legacy_route | `core/planning/planner.py` | 2105 | deprecated_reference: fallback_task_name: str, |
| low | legacy_route | `core/planning/planner.py` | 2113 | deprecated_reference: task_name = str(item.get("task_name") or fallback_task_name).strip() or fallback_task_name |
| low | legacy_route | `core/planning/planner.py` | 2121 | deprecated_reference: normalized.setdefault("legacy_plan_contract", False) |
| low | legacy_route | `core/planning/planner_contract.py` | 233 | deprecated_reference: step["legacy_plan_contract"] = False |
| low | legacy_route | `core/planning/planner_contract.py` | 274 | deprecated_reference: "legacy_plan_contract": bool(step.get("legacy_plan_contract", False)), |
| low | legacy_route | `core/planning/planner_contract_trace.py` | 75 | deprecated_reference: "scheduler_planner_legacy_fallback_used": _optional_bool( |
| low | legacy_route | `core/planning/planner_contract_trace.py` | 76 | deprecated_reference: safe_payload.get("scheduler_planner_legacy_fallback_used") |

Truncated: 2838 additional non-mainline findings are in JSON.

## Interpretation

This audit is intentionally conservative. A finding is not automatically a bug.
Use it to decide which legacy paths require tests, removal, or explicit documentation.

Recommended next action:

1. Review all critical/high findings outside `tests/` and `tools/`.
2. For each real runtime bypass, either route through the governed authority path or document why it is safe.
3. For each legacy status alias, confirm it is canonicalized before it reaches RuntimeState/ExecutionResult.
4. Keep non-mainline findings visible instead of silently skipping them.
