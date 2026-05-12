# Scheduler Extraction Target Audit v2

## Purpose

This document records the next scheduler extraction target audit after the first successful `pure_helpers` extraction passes.

The purpose is not to split more code immediately.

The purpose is to prevent unsafe extraction by classifying what was proven safe, what was rejected, and what should remain untouched until stronger regression coverage exists.

## Current checkpoint

The scheduler extraction process has reached this state:

```text
runtime transaction / verify / rollback boundary: sealed
scheduler responsibility audit: completed
scheduler extraction plan: completed
pure helper extraction v1: completed
pure helper extraction v2: completed
trace payload extraction attempt: rejected / reverted
working tree: clean
```

Completed extraction commits:

```text
08b2d22 - refactor: extract scheduler pure helpers
de839f5 - refactor: extract scheduler canonicalize helper
```

Current extracted helper module:

```text
core/tasks/scheduler_core/pure_helpers.py
```

Extracted helpers:

```text
_safe_int_for_runtime_gate
_extract_task_id
_strip_quotes
_extract_file_path
_canonicalize_steps_for_compare
```

## Confirmed safe extraction pattern

The successful extraction pattern is:

```text
small helper
no self state dependency
no queue lifecycle mutation
no task state transition mutation
no execution dispatch
no StepExecutor dependency
no ExecutionGuard dependency
no transaction / verify / rollback coupling
no persistence write path
compile check passes
StepExecutor smoke remains stable
```

This is the only extraction style that should continue for now.

## Rejected extraction attempt: trace payload helpers

A trace payload extraction attempt was tested and reverted.

Attempted target:

```text
_extract_execution_trace_from_payload
_promote_execution_trace_in_executed_results
```

Proposed module:

```text
core/tasks/scheduler_core/trace_payload_helpers.py
```

Result:

```text
reverted
```

Reason:

These scheduler methods were already thin wrappers around existing helper functions:

```text
extract_execution_trace_from_payload(...)
promote_execution_trace_in_executed_results(...)
```

Moving them into a new helper module did not extract meaningful scheduler logic. It only added another wrapper layer.

That increased risk without reducing scheduler responsibility.

Rejected because:

```text
not real extraction
adds indirection
does not reduce responsibility
can introduce missing imports / runtime breakage
low value
```

Conclusion:

```text
Do not extract trace payload wrappers unless the existing helper ownership is redesigned.
```

## Current target classification

### A. Already extracted / do not revisit

```text
_safe_int_for_runtime_gate
_extract_task_id
_strip_quotes
_extract_file_path
_canonicalize_steps_for_compare
```

These are complete for now.

Do not repeatedly move or rename them unless there is a clear module ownership reason.

### B. Safe only after direct source inspection

These may be possible future candidates, but must be inspected one by one before extraction:

```text
_normalize_depends_on_simple
_normalize_verify_step
_infer_completion_fields
_clear_stale_replan_fields
_safe_read_json
_is_fatal_failure_text
_sync_blocked_state
_append_history
_extract_function_name_for_fix
_infer_known_multi_function_targets_from_goal
_extract_python_file_paths
_is_shared_like_path
_strip_markdown_code_fences
_should_force_deterministic_task_planner
_extract_all_document_file_paths
_extract_document_arrow_paths
_parse_inline_step
_looks_like_hello_world_python
```

Rules before extraction:

```text
print exact function body
confirm no self dependency
confirm no persistence write path
confirm no task state mutation
confirm no planner behavior change
extract one small group only
compile before commit
run StepExecutor smoke before commit
```

### C. Low value / do not extract now

These look small, but are not good next targets because they are wrappers or already delegate elsewhere:

```text
_extract_execution_trace_from_payload
_promote_execution_trace_in_executed_results
_resolve_explicit_agent_loop
_should_fallback_to_simple_runner
_is_simple_runner_eligible_fallback
_run_simple_task_tick
```

Do not extract wrappers just to reduce line count.

Extraction must reduce responsibility, not add another pass-through layer.

### D. Requires regression before extraction

These may be extractable later, but only after dedicated regression tests exist:

```text
_extract_text_from_result_payload
_normalize_public_status_fields
_is_legacy_self_edit_scheduler_task
_is_autonomous_repair_task
_extract_repair_target_path_from_text
_repo_edit_context_path_requires_core
_extract_paths_from_text
_summarize_forced_repo_edit_result
_call_planner_like
_normalize_external_plan
_try_plan_command
_apply_builtin_function_fix
```

Risk:

```text
planner behavior
repair detection behavior
public status behavior
code-chain behavior
document / command parsing behavior
```

These are not first-choice targets for the next extraction pass.

### E. Do not touch now

These are runtime-bound, queue-bound, repair-bound, or persistence-bound.

Do not extract blindly:

```text
tick
_apply_runtime_dispatch_gate_to_ready_queue
_runtime_dispatch_gate_decision
_build_tick_result
_can_requeue_task
_run_task_via_agent_loop
run_one_step
_run_task_via_agent_loop_with_fallback_check
_handle_simple_step_exception
_fallback_handle_simple_step_exception
_try_replan_task
apply_replan_task
preview_replan_task
_execute_simple_step
_run_execution_gateway_basic_step
_record_execution_gateway_side_check
_refresh_task_public_fields
_trace_status
_trace_step
cleanup_task_queue_hygiene
_fail_task_for_queue_hygiene
_validate_repair_task_scope
_repair_task_fingerprint_from_goal
_repair_task_fingerprint_from_task
_expire_duplicate_repair_task_if_stale
_find_active_duplicate_repair_task
_register_repair_fingerprint_for_task
_read_repo_edit_code_context
_extract_repo_edit_context_paths
_try_force_repo_edit_at_create_task
_create_task_record
_pre_enqueue_repair_fingerprint_gate
create_task
submit_task
submit_existing_task
pause_task
resume_task
cancel_task
set_task_priority
_set_status
_force_repo_task_state
_ensure_task_paths
_extract_result_artifact_paths
_normalize_task_schema
_backfill_replan_decision_fields
_verify_step_failure_repairable
_hydrate_task_from_workspace
_collapse_non_retryable_retrying_task
_persist_task_payload
_save_task_snapshot_safe
_get_task_from_repo
_list_repo_tasks
_ensure_executable_steps_for_task
_try_plan_multi_function_fix
_list_python_functions_in_file
_try_plan_function_fix
_find_python_file_containing_function
_execute_multi_code_edit_step
_execute_code_edit_step
_resolve_code_edit_abs_path
_plan_goal_via_forced_deterministic_planner
_plan_goal
_plan_goal_via_agent_planners
_parse_goal_overrides
_extract_document_source_path
_extract_document_output_path
_extract_document_task_payload
_try_plan_write_file
_extract_write_content
```

These areas are too close to:

```text
queue lifecycle
task lifecycle
execution dispatch
repair / replan chain
planner behavior
runtime persistence
transaction / verify / rollback boundary
```

They require a separate extraction plan and stronger tests.

## Recommended next target

Do not continue trace extraction.

The next safest useful target is:

```text
Scheduler Parsing Helper Inspection v1
```

Candidate group:

```text
_strip_markdown_code_fences
_extract_python_file_paths
_is_shared_like_path
_extract_all_document_file_paths
_extract_document_arrow_paths
_parse_inline_step
_looks_like_hello_world_python
```

However, before extraction, each function body must be printed and checked.

The first action should be inspection only:

```text
print exact function bodies
check for self
check for hidden planner assumptions
check for regex import requirements
check for duplicate logic with pure_helpers.py
```

If inspection passes, extract only one subgroup:

```text
path / text parsing helpers
```

Do not combine with planner behavior.

## Guardrails for the next extraction

Before changing code:

```text
1. Print exact target function bodies.
2. Confirm no self dependency.
3. Confirm no task state mutation.
4. Confirm no queue mutation.
5. Confirm no persistence writes.
6. Confirm no StepExecutor / ExecutionGuard coupling.
7. Confirm no transaction / verify / rollback coupling.
8. Confirm the extraction reduces real responsibility, not only line count.
```

After changing code:

```text
python -m py_compile core/tasks/scheduler.py core/tasks/scheduler_core/<new_helper>.py
python tests/test_step_executor.py
git diff --stat
git status
```

Commit only if:

```text
small diff
compile passes
StepExecutor smoke passes
no temporary files
working tree contains only intended source files
```

## Current conclusion

The scheduler extraction pipeline is valid, but only for carefully selected helpers.

The next phase should be:

```text
inspect -> classify -> extract one small useful group -> verify -> commit
```

not:

```text
scan -> bulk extract -> repair breakage
```

This keeps the runtime transaction / verification boundary sealed while gradually reducing scheduler responsibility.
