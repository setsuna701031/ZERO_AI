# Scheduler Extraction Audit

Status: active extraction audit

Date: 2026-05-16

Target file:

```text
core/tasks/scheduler.py
```

Current observed line count:

```text
8256
```

## Audit Scope

This audit covers scheduler extraction work that has already been moved into helper modules.

This audit does not approve changes to:

- `tick()`
- dispatch flow
- runtime queue state transition
- repair flow
- resume flow
- public method signatures
- filesystem path policy
- trace event format

## Extraction Inventory

### Command Planning

Helper:

```text
core/tasks/scheduler_core/command_planner.py
```

Scheduler wrapper:

```text
Scheduler._try_plan_command(...)
```

Behavior covered:

- non-command inline task goals do not become command steps
- `run ...`
- `command: ...`
- `powershell ...`
- mojibake regex crash removed from scheduler path

Tests:

```text
tests/test_scheduler_command_planner.py
```

### Path Parsing

Helper:

```text
core/tasks/scheduler_core/path_parser_helpers.py
```

Scheduler wrappers:

```text
Scheduler._extract_python_file_paths(...)
Scheduler._is_shared_like_path(...)
Scheduler._strip_markdown_code_fences(...)
Scheduler._extract_all_document_file_paths(...)
Scheduler._extract_document_arrow_paths(...)
Scheduler._extract_document_source_path(...)
Scheduler._extract_document_output_path(...)
Scheduler._extract_file_path(...)
```

Compatibility wrapper:

```text
core/tasks/scheduler_core/pure_helpers._extract_file_path(...)
```

Behavior covered:

- Python file path extraction
- shared path detection
- markdown code fence stripping
- document file path extraction
- document arrow source/output parsing
- document source path fallback
- document output path fallback
- scheduler wrapper compatibility

Tests:

```text
tests/test_scheduler_parser_helpers.py
```

### Queue Formatting

Helper:

```text
core/tasks/scheduler_core/queue_formatting_helpers.py
```

Scheduler methods kept as public API:

```text
Scheduler.get_queue_rows()
Scheduler.get_queue_snapshot()
```

Behavior covered:

- queue row payload formatting
- queue snapshot payload formatting
- review queue inclusion filtering
- review queue closed-status exclusion

Tests:

```text
tests/test_scheduler_queue_formatting_helpers.py
```

Boundary note:

```text
The helper formats queue data only.
It does not mutate runtime queue state.
It does not dispatch tasks.
It does not change worker lifecycle.
```

### Public Task Record Formatting

Helper:

```text
core/tasks/scheduler_core/public_task_record_helpers.py
```

Scheduler wrapper:

```text
Scheduler._normalize_public_status_fields(...)
```

Behavior covered:

- status normalization
- current step display fields
- state detail formatting
- history fallback
- public snapshot formatting remains helper-owned

Tests:

```text
tests/test_scheduler_queue_formatting_helpers.py
tests/test_scheduler_parser_helpers.py
```

### Trace Serialization / Load / Save

Helper:

```text
core/tasks/scheduler_core/trace_serialization_helpers.py
```

Trace event helper remains:

```text
core/tasks/scheduler_core/trace_helpers.py
```

Scheduler wrappers still present:

```text
Scheduler._extract_execution_trace_from_payload(...)
Scheduler._promote_execution_trace_in_executed_results(...)
Scheduler._load_trace_for_task(...)
Scheduler._save_trace_for_task(...)
Scheduler._trace_status(...)
```

Behavior covered:

- empty trace payload
- normal trace list promotion
- missing trace file defensive fallback
- malformed JSON defensive fallback
- save preserves existing `ExecutionTrace` format

Tests:

```text
tests/test_scheduler_trace_serialization_helpers.py
tests/test_scheduler_trace_runtime_load_redirect.py
tests/test_scheduler_trace_runtime_save_redirect.py
```

Boundary note:

```text
Trace serialization extraction does not change trace event format.
Trace file resolution keeps the existing policy path.
Trace event helpers remain separate from load/save serialization helpers.
```

## Current Test Coverage

Latest focused helper test group:

```text
pytest tests/test_scheduler_command_planner.py tests/test_scheduler_parser_helpers.py tests/test_scheduler_queue_formatting_helpers.py tests/test_scheduler_trace_serialization_helpers.py tests/test_scheduler_trace_runtime_load_redirect.py tests/test_scheduler_trace_runtime_save_redirect.py -q
```

Recorded result:

```text
32 passed
```

Compile check:

```text
python -m py_compile core/tasks/scheduler.py core/tasks/scheduler_core/command_planner.py core/tasks/scheduler_core/path_parser_helpers.py core/tasks/scheduler_core/queue_formatting_helpers.py core/tasks/scheduler_core/public_task_record_helpers.py core/tasks/scheduler_core/trace_helpers.py core/tasks/scheduler_core/trace_serialization_helpers.py
```

Recorded result:

```text
passed
```

Import-cycle check:

```text
import core.tasks.scheduler_core.trace_serialization_helpers
import core.tasks.scheduler_core.trace_helpers
import core.tasks.scheduler_core.queue_formatting_helpers
import core.tasks.scheduler_core.public_task_record_helpers
import core.tasks.scheduler_core.path_parser_helpers
import core.tasks.scheduler_core.pure_helpers
import core.tasks.scheduler
```

Recorded result:

```text
passed
```

## Remaining High-Risk Scheduler Areas

Do not extract or alter these without a dedicated plan:

- `tick()` and tick shims
- dispatch round handling
- worker lifecycle
- runtime queue state transitions
- repair task enqueue lifecycle
- resume gate behavior
- mutation/recovery/replay coordination
- persistence write paths
- filesystem path policy
- command execution policy

## Pending Runtime Compatibility Issue

Known issue:

```text
AttributeError: 'Scheduler' object has no attribute '_handle_dispatch_result'
```

Observed context:

```text
Scheduler.tick()
-> execute_dispatch_round(...)
-> dispatch_helpers expects scheduler._handle_dispatch_result(...)
```

Audit decision:

```text
This is a pending runtime compatibility issue.
It is not fixed in this extraction audit.
It must be handled separately because it touches tick/dispatch compatibility.
```

## Freeze Rule

Future scheduler extraction work must satisfy all of the following:

1. No new runtime behavior.
2. No public method signature changes.
3. `scheduler.py` keeps compatibility wrappers where callers still depend on them.
4. Helper modules stay side-effect scoped to their responsibility.
5. Tests are added or strengthened with the extraction.
6. py_compile and import-cycle checks pass.
7. Known runtime compatibility issues are recorded rather than fixed opportunistically.

