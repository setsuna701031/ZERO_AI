# ZERO Scheduler Extraction Plan v1

## Purpose

This document defines the planned extraction order for `core/tasks/scheduler.py`.

This is a planning checkpoint only.

It does not change runtime behavior, does not split files, and does not modify the scheduler implementation.

The goal is to reduce scheduler responsibility pressure safely without breaking the recently sealed runtime transaction, verification, rollback, and regression boundaries.

## Current rule

Do not extract code until the target responsibility is clearly classified as low risk and has an existing stable behavior boundary.

The correct order is:

```text
audit
-> extraction plan
-> low-risk helper extraction
-> validation
-> next extraction
```

Do not do:

```text
large scheduler rewrite
-> behavior drift
-> emergency repair
```

## Extraction principles

### 1. Preserve runtime behavior first

The scheduler is currently a compatibility and orchestration surface.

Extraction must not change:

* task lifecycle semantics
* queue behavior
* task status transitions
* execution dispatch behavior
* patch transaction behavior
* verify / rollback behavior
* guard / policy behavior
* trace persistence
* CLI compatibility

### 2. Extract only one responsibility group at a time

Each extraction should move one clearly bounded responsibility.

Do not combine:

* formatting cleanup
* behavior changes
* helper extraction
* policy changes
* new features

in the same patch.

### 3. Prefer pure helpers first

The first extraction candidates should be functions that:

* do not mutate scheduler state directly
* do not call StepExecutor directly
* do not call ExecutionGuard directly
* do not change task lifecycle state
* do not touch persistence except through explicit arguments
* are easy to test with small input/output fixtures

### 4. Keep transaction / verify / rollback sealed

The recently sealed patch runtime chain must remain intact:

```text
preflight
-> transaction
-> backup snapshot
-> apply
-> verify
-> commit / rollback
```

Scheduler extraction must not move this logic back into scheduler.

### 5. Scheduler remains orchestration

Scheduler should keep responsibility for high-level orchestration:

* accepting task operations
* coordinating queue lifecycle
* calling planning/runtime/execution boundaries
* recording task status through existing repository/runtime paths
* preserving CLI compatibility

Scheduler should not become:

* patch engine
* verification engine
* display renderer
* policy engine
* audit database
* tool-specific executor

## Responsibility groups

### A. Keep inside scheduler for now

These areas are high risk and should remain in `scheduler.py` until surrounding contracts are stronger:

* task lifecycle entrypoints
* queue lifecycle entrypoints
* public scheduler API methods
* CLI-facing compatibility methods
* status transition coordination
* handoff to TaskRuntime / TaskRepository
* execution dispatch entrypoints
* compatibility glue for legacy task records

Reason:

These areas are likely coupled to app.py, CLI behavior, task state persistence, and existing smoke expectations.

### B. Candidate for low-risk extraction

These areas can be extracted first if they are currently mixed into scheduler:

* display / formatting helpers
* task summary rendering
* task list formatting
* status label normalization for presentation
* small validation helpers
* pure metadata normalization helpers
* path display formatting
* repeated dictionary extraction / coercion helpers

Reason:

They should not alter task execution behavior if extracted carefully.

### C. Candidate for medium-risk extraction

These areas can be extracted after low-risk helpers are stable:

* trace / audit payload shaping
* runtime metadata hydration helpers
* queue status filtering helpers
* task record normalization helpers
* planner context preparation helpers
* repair context preparation helpers

Reason:

They affect how state is represented and observed, but should not directly execute work if boundaries are kept clear.

### D. High-risk extraction

These should not be touched until more tests and clearer contracts exist:

* execution dispatch
* step execution bridge
* patch / repair orchestration
* verify / rollback handoff
* queue rebuild behavior
* task state transitions
* planner fallback behavior
* legacy compatibility behavior
* repo/runtime persistence write paths

Reason:

These areas can silently break task execution, rollback safety, or CLI compatibility.

## Recommended extraction order

### Phase 1: Presentation / formatting helpers

Target module proposal:

```text
core/tasks/scheduler_core/display_helpers.py
```

Candidate responsibilities:

* task status display formatting
* task list row shaping
* result summary formatting
* safe truncation helpers
* human-readable task metadata presentation

Acceptance criteria:

* no task lifecycle behavior changes
* no scheduler state mutation
* no StepExecutor / ExecutionGuard dependency
* existing task list behavior remains compatible

Suggested validation:

```powershell
python -m py_compile core/tasks/scheduler.py core/tasks/scheduler_core/display_helpers.py
python app.py task list
```

### Phase 2: Metadata normalization helpers

Target module proposal:

```text
core/tasks/scheduler_core/metadata_helpers.py
```

Candidate responsibilities:

* safe dictionary access
* task metadata normalization
* runtime metadata merge helpers
* status field normalization
* optional field defaulting

Acceptance criteria:

* helpers remain pure or near-pure
* no execution behavior changes
* no persistence writes inside helpers unless explicitly existing and preserved

Suggested validation:

```powershell
python -m py_compile core/tasks/scheduler.py core/tasks/scheduler_core/metadata_helpers.py
python tests/test_scheduler_smoke.py
```

### Phase 3: Trace / audit shaping helpers

Target module proposal:

```text
core/tasks/scheduler_core/audit_trace_helpers.py
```

Candidate responsibilities:

* trace event payload shaping
* audit metadata shaping
* execution event summaries
* non-mutating trace formatting

Acceptance criteria:

* trace contents remain compatible
* no execution behavior changes
* no queue behavior changes
* no hidden file writes introduced

Suggested validation:

```powershell
python -m py_compile core/tasks/scheduler.py core/tasks/scheduler_core/audit_trace_helpers.py
python tests/test_step_executor.py
```

### Phase 4: Planner context preparation helpers

Target module proposal:

```text
core/tasks/scheduler_core/planner_context_helpers.py
```

Candidate responsibilities:

* building planner context dictionaries
* preserving user goal / source / output fields
* extracting document-task context
* normalizing repair planning context

Acceptance criteria:

* no planner policy changes
* no fallback behavior changes
* document flow remains stable
* repair flow remains stable

Suggested validation:

```powershell
python -m py_compile core/tasks/scheduler.py core/tasks/scheduler_core/planner_context_helpers.py
python tests/run_mainline_smoke.py
```

### Phase 5: Queue filter helpers

Target module proposal:

```text
core/tasks/scheduler_core/queue_filter_helpers.py
```

Candidate responsibilities:

* deciding which tasks are visible to queue scan
* filtering terminal states
* filtering blocked/waiting states
* simple queue readiness predicates

Acceptance criteria:

* created tasks do not auto-run
* failed/replanning tasks do not block unrelated normal tasks
* submitted/queued tasks still run normally
* legacy task records remain compatible

Suggested validation:

```powershell
python tests/run_multi_task_demo_smoke.py
python tests/run_mainline_smoke.py
```

### Phase 6: Execution dispatch boundary review only

No extraction yet.

At this phase, only review whether dispatch responsibilities can be isolated later.

Do not move:

* StepExecutor calls
* ExecutionGuard calls
* patch transaction handoff
* verify / rollback handoff
* task state mutation
* runtime persistence writes

until there is stronger regression coverage.

## Do-not-touch zones for now

The following should not be extracted in the next pass:

```text
apply_patch handling
patch transaction metadata
verify / commit boundary
rollback behavior
repo_source confirmation gate
execution guard decision path
StepExecutor construction / invocation
TaskRuntime persistence writes
task state transition write paths
legacy compatibility fallback paths
```

These zones are recently stabilized and should remain untouched until the scheduler has passed at least one low-risk extraction round.

## First real extraction recommendation

The first actual code extraction should be:

```text
Scheduler Display / Formatting Helpers v1
```

Reason:

It is the lowest-risk scheduler responsibility group.

Expected scope:

```text
core/tasks/scheduler.py
-> move display-only helpers to
core/tasks/scheduler_core/display_helpers.py
```

Strict rules:

* no runtime behavior change
* no execution behavior change
* no queue behavior change
* no transaction / verify / rollback changes
* no policy changes
* no planner changes

## Checkpoint definition

This planning checkpoint is complete when:

* `docs/scheduler_extraction_plan.md` exists
* no runtime code is changed
* `git status --short` shows only the new doc before commit
* next extraction target is clearly identified as display / formatting helpers

## Next step after this document

Proceed to:

```text
Scheduler Display Helpers Extraction v1
```

only after committing this document.
