# Runtime Boundary Freeze Manifest

Status: scheduler extraction freeze manifest

Date: 2026-05-16

Scope:

- Documentation only.
- No scheduler.py code changes in this checkpoint.
- No runtime behavior changes in this checkpoint.
- No tick, dispatch, runtime queue, repair, or resume changes.
- No public method signature changes.

## Freeze Intent

This manifest records the current scheduler extraction boundary after a set of small, tested helper extractions.

The goal is not to declare the runtime fully sealed. The goal is to make the current boundary explicit so future work does not accidentally add new behavior to `core/tasks/scheduler.py` or widen the scheduler's responsibilities.

## Current Scheduler Baseline

Current observed scheduler size:

```text
core/tasks/scheduler.py: 8256 lines
```

The scheduler remains a high-risk orchestration file. It still owns broad compatibility surfaces and multiple legacy shims. It should be treated as frozen for new behavior.

## Frozen Boundaries

Do not change these areas during scheduler slimming unless a dedicated compatibility plan and regression target are approved:

- `tick()`
- dispatch flow
- runtime queue state transition
- repair flow
- resume flow
- public method signatures
- filesystem path policy
- trace event format
- execution permission semantics

## Allowed Scheduler Work

Allowed work during this freeze:

- Move pure formatting, parsing, or serialization helpers out of `scheduler.py`.
- Keep `scheduler.py` wrappers when compatibility callers still exist.
- Add focused helper tests before or with extraction.
- Run the helper test group and import-cycle check after each extraction.
- Document pending compatibility issues without opportunistically fixing them.

## Disallowed Scheduler Work

Do not use extraction checkpoints to:

- add new runtime capability
- change queue state transitions
- change dispatch behavior
- change repair or resume semantics
- change trace event schema
- change path resolution policy
- fix unrelated runtime failures
- hide compatibility failures behind broad exception handling

## Current Helper Ownership

Extracted helper ownership currently includes:

```text
core/tasks/scheduler_core/command_planner.py
  - command planning parsing

core/tasks/scheduler_core/path_parser_helpers.py
  - path parsing helpers
  - document source/output path extraction
  - markdown code fence stripping

core/tasks/scheduler_core/queue_formatting_helpers.py
  - queue row payload formatting
  - queue snapshot payload formatting
  - review queue display filtering

core/tasks/scheduler_core/public_task_record_helpers.py
  - public task record formatting
  - public status field normalization

core/tasks/scheduler_core/trace_serialization_helpers.py
  - execution trace payload extraction
  - trace promotion in executed results
  - trace file resolution through existing policy
  - trace load/save defensive behavior

core/tasks/scheduler_core/trace_helpers.py
  - trace event helper behavior
```

## Required Test Group

For scheduler helper extraction checkpoints, run at minimum:

```text
pytest tests/test_scheduler_command_planner.py tests/test_scheduler_parser_helpers.py tests/test_scheduler_queue_formatting_helpers.py tests/test_scheduler_trace_serialization_helpers.py tests/test_scheduler_trace_runtime_load_redirect.py tests/test_scheduler_trace_runtime_save_redirect.py -q
```

Current recorded result:

```text
32 passed
```

Also run:

```text
python -m py_compile core/tasks/scheduler.py core/tasks/scheduler_core/command_planner.py core/tasks/scheduler_core/path_parser_helpers.py core/tasks/scheduler_core/queue_formatting_helpers.py core/tasks/scheduler_core/public_task_record_helpers.py core/tasks/scheduler_core/trace_helpers.py core/tasks/scheduler_core/trace_serialization_helpers.py
```

Current recorded result:

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

Current recorded result:

```text
passed
```

## Pending Compatibility Issue

Known pending runtime compatibility issue:

```text
Scheduler.tick() can fail when dispatch_helpers expects scheduler._handle_dispatch_result.
Observed failure:
AttributeError: 'Scheduler' object has no attribute '_handle_dispatch_result'
```

Freeze decision:

```text
Do not fix this in scheduler extraction checkpoints.
Track it as a separate runtime compatibility issue.
It touches dispatch/tick compatibility and is outside helper extraction scope.
```

## Next Safe Work

The next safe extraction work should continue to target pure helper boundaries only.

Recommended order:

1. Add tests for the specific helper behavior.
2. Move pure logic into `scheduler_core`.
3. Keep compatibility wrappers in `scheduler.py`.
4. Run helper tests, py_compile, and import-cycle check.
5. Record line-count change and any blocked runtime compatibility issue.

