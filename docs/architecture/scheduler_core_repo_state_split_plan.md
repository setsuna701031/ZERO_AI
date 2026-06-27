# Scheduler Core Repo State Split Plan

## Current State

`core/tasks/scheduler_core/repo_state_helpers.py` is now a compatibility facade. It exports stable names for older imports and delegates to extracted implementation modules.

Implementation modules no longer import `repo_state_helpers.py`.

## External Public Helpers

These names remain stable through the facade:

- `attach_repo_runtime_state_adapter_payload`
- `build_failure_observability_event`
- `build_repo_runtime_state_adapter_payload`
- `compact_runner_result`
- `extract_effective_status_and_answer`
- `get_task_from_repo`
- `list_repo_tasks`
- `mark_repo_task_failed`
- `mark_repo_task_finished`
- `mark_repo_task_queued`
- `mark_repo_task_with_adapter`
- `sync_blocked_state`
- `sync_runtime_back_to_repo`
- `sync_unblocked_state`

Compatibility private helpers still exported by the facade:

- `_advisory_transition_reason`
- `_append_status_to_history`
- `_downgrade_advisory_blocked_status`
- `_has_remaining_steps`
- `_is_successful_nonblocking_step_result`
- `_repo_runtime_adapter_error_text`
- `_repo_runtime_adapter_error_type`
- `_repo_runtime_adapter_execution_trace`
- `_repo_runtime_adapter_final_answer`
- `_repo_runtime_adapter_last_result`
- `_repo_runtime_adapter_message`
- `_repo_runtime_adapter_ok`
- `_repo_runtime_adapter_runtime_mode`
- `_save_runtime_state_from_merged`
- `_select_effective_task_payload`
- `_should_downgrade_advisory_blocked_status`
- `_sync_loop_fields_into_merged`
- `_sync_review_fields_into_merged`

## Completed Split

- `repo_observability.py`: failure/retry observability envelope.
- `repo_runtime_adapter.py`: runtime adapter payload construction and adapter field extraction.
- `repo_task_state.py`: repo task lookup, runner result compaction, and queued/failed/finished task marking.
- `repo_blocked_state.py`: blocked/unblocked synchronization and advisory blocked downgrade helpers.
- `repo_runtime_sync.py`: runtime-state merge, runtime saveback, and status routing back to repo task state.

## Import Boundary

```text
repo_state_helpers.py
  -> repo_observability.py
  -> repo_runtime_adapter.py
  -> repo_task_state.py
  -> repo_blocked_state.py
  -> repo_runtime_sync.py

repo_runtime_sync.py
  -> repo_runtime_adapter.py
  -> repo_task_state.py
  -> repo_blocked_state.py

repo_task_state.py
  -> repo_observability.py
```

No extracted implementation module imports `repo_state_helpers.py`.

## Validation

Required validation:

1. `python -m pytest tests/test_repo_observability.py tests/test_repo_runtime_adapter.py tests/test_repo_task_state.py tests/test_repo_runtime_sync.py tests/test_repo_blocked_state.py -q`
2. `python -m pytest tests -q -k scheduler`
3. `python -m compileall core tests tools`
