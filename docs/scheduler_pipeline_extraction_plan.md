# Scheduler Pipeline Extraction Plan

## Current Baseline

- Scheduler completion/operator consolidation committed.
- Working tree clean before this document.
- Verified:
  - scheduler/operator/completion targeted tests passed.
  - scheduler/operator/completion regression passed.
  - runtime/scheduler/operator/completion/dispatch/work_package regression passed.

## Current Risk

`core/tasks/scheduler.py` still contains historical monkey-patch layers:

- multiple `Scheduler.run_one_step = ...`
- multiple `_zero_scheduler_base_run_one_step_*`
- legacy wrapper chain from v16 down through v8/v7/v6/v5/v4/v3/v2 and older overlays.

Do not remove any layer until its responsibility is covered by tests and mapped to a replacement module.

## Target Modules

### 1. `core/tasks/scheduler_core/scheduler_progress.py`

Owns:

- `current_step_index`
- `next_step_index`
- task step progress mutation

Candidate functions:

- `_zero_scheduler_update_step_progress`

### 2. `core/tasks/scheduler_core/scheduler_completion.py`

Owns:

- operator registry completion
- operator registry failure
- completed_steps fallback
- missing completion detection

Candidate functions:

- `_zero_scheduler_complete_operator`
- `_zero_scheduler_mark_completed_steps_fallback`
- `_zero_scheduler_mark_operator_complete_if_ok`
- `_zero_scheduler_mark_operator_complete_or_failed`
- `_zero_scheduler_mark_failed_step_if_needed`
- `_zero_scheduler_mark_failed_if_ok_without_completion`
- `_zero_scheduler_run_operator_completion_pipeline`

### 3. `core/tasks/scheduler_core/scheduler_runtime_fallback.py`

Owns:

- runtime gate fallback
- explicit authority fallback
- direct handler fallback

Candidate layers:

- v2
- v3
- v4
- v5

### 4. `core/tasks/scheduler_core/scheduler_pipeline.py`

Owns final `run_one_step` orchestration:

1. call base scheduler execution
2. apply runtime fallback if required
3. update step progress
4. apply operator completion pipeline
5. return canonical result

## Migration Order

### Phase 1: Extract progress helper

Move progress mutation into `scheduler_progress.py`.

Constraints:

- behavior must remain identical
- keep compatibility import in `scheduler.py`
- run scheduler/operator/completion tests

### Phase 2: Extract completion helpers

Move completion and failure helpers into `scheduler_completion.py`.

Constraints:

- no behavior change
- registry calls must preserve order
- completed_steps fallback must remain intact
- missing completion failure seal must remain intact

### Phase 3: Extract runtime fallback helpers

Move v2-v5 fallback logic into `scheduler_runtime_fallback.py`.

Constraints:

- do not collapse wrappers yet
- only move helper logic after tests cover behavior

### Phase 4: Collapse v6/v7/v8 wrappers

Only after progress and completion modules are extracted.

Target:

- keep one compatibility wrapper
- remove duplicated progress/completion side effects
- preserve final `Scheduler.run_one_step.__name__`

### Phase 5: Collapse v2-v5 fallback wrappers

Only after runtime fallback module is tested.

Target:

- one runtime fallback pipeline
- no repeated `Scheduler.run_one_step = ...` layers

## Non-Mainline Issue Reporting

If issues outside this migration scope are discovered, record them explicitly instead of silently skipping them.

Do not fix unrelated issues inside the same commit unless they block this migration.
