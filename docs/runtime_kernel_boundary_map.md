# ZERO Runtime Kernel Boundary Map

## Phase10 Purpose

Phase10 is not a cleanup phase.

The goal is to protect the remaining runtime kernel boundaries before any deeper scheduler split.

Current direction:

- Preserve scheduler.py as the orchestration kernel.
- Keep implementation-heavy runtime behavior inside scheduler_core/* or dedicated runtime modules.
- Avoid removing code only because it is long.
- Do not split persistence, hydration, planner, or repair logic until their ownership contract is explicit.

## Current Scheduler Position

After Phase8 and Phase9, scheduler.py has been reduced from a mixed runtime owner into a thinner orchestration shell.

Known checkpoints:

- Phase8 orchestration hollowing: 7467 lines / 164 defs / 165 tests passed.
- Phase9 public adapter extraction: 7292 lines / 161 defs / 165 tests passed.
- Phase9 dispatch wrapper cleanup: 7234 lines / 155 defs / 165 tests passed.

## Ownership Already Moved Out

The following responsibilities have already moved out of scheduler.py and should stay out:

### Trace Runtime / Trace Helpers

Owner:

- core/tasks/scheduler_core/trace_helpers.py
- core/runtime/trace_runtime.py

Scheduler should not re-own trace formatting, trace file routing, or trace event helper logic.

### Step Path Helpers

Owner:

- core/tasks/scheduler_core/step_path_helpers.py

Scheduler should not re-own path normalization, shared/workspace/sandbox path resolution, or result payload text extraction when helper ownership already exists.

### Simple Runtime Execution Helpers

Owner:

- core/tasks/scheduler_core/simple_runner_helpers.py
- core/tasks/scheduler_core/simple_step_executor_helpers.py
- core/tasks/scheduler_core/command_step_helpers.py
- core/tasks/scheduler_core/llm_step_helpers.py

Scheduler should not re-own simple task terminal/block/finish/step-success/step-error handler logic.

### Public Task Record Adapter

Owner:

- core/tasks/scheduler_core/public_task_record_helpers.py

Scheduler should not re-own public task record formatting, public snapshot shaping, or UI/API-friendly task projection logic.

### Dispatch Helper Layer

Owner:

- core/tasks/scheduler_core/dispatch_helpers.py
- core/tasks/scheduler_core/task_dispatcher.py
- core/tasks/scheduler_core/task_scheduler_queue.py
- core/tasks/scheduler_core/worker_pool.py

Scheduler should not re-own dispatch result wrappers or dispatcher compatibility wrappers.

## Remaining Scheduler Kernel Ownership

The following areas still live in scheduler.py and should be treated as kernel-level until proven otherwise.

### Runtime Persistence Kernel

Representative functions:

- _persist_task_payload
- _save_task_snapshot_safe
- _write_runtime_state_file_safe

Current rule:

Do not split only to reduce line count. Persistence touches task files, runtime state, snapshots, and repository sync. A bad split can break resume/replay behavior.

Possible future extraction:

- core/tasks/scheduler_core/task_persistence_kernel.py

Only extract after defining:

- input contract
- output contract
- failure behavior
- atomic write behavior
- snapshot/runtime_state consistency

### Runtime Hydration Kernel

Representative functions:

- _hydrate_task_from_workspace
- _ensure_task_paths
- _refresh_task_public_fields usage path

Current rule:

Do not extract blindly. Hydration is restart/recovery behavior and controls how persisted runtime state becomes executable task state.

Possible future extraction:

- core/tasks/scheduler_core/task_hydration_kernel.py

Only extract after defining:

- what source of truth wins when task repo, plan file, runtime state file, and trace file disagree
- how blocker/review state resumes
- how current_step_index and step_results are restored

### Planner Kernel

Representative functions:

- _plan_goal
- _try_plan_write_file
- _try_plan_read_file
- _try_plan_command
- _parse_inline_step

Current rule:

Do not mix planner extraction with runtime extraction. Planner logic has its own risk because it controls task creation semantics.

Possible future extraction:

- core/tasks/scheduler_core/planner_kernel.py

Only extract after defining:

- deterministic planner contract
- fallback planner order
- document flow parsing rules
- write/read/command planning rules

### Repair Kernel

Representative functions:

- _is_repairable_failure
- _try_replan_task
- apply_replan_task
- preview_replan_task
- _failed_replan_fingerprints

Current rule:

Do not split repair during scheduler hollowing unless the repair lifecycle contract is documented. Repair touches planner, task state, runtime status, requeue behavior, and safety limits.

Possible future extraction:

- core/tasks/scheduler_core/repair_kernel.py

Only extract after defining:

- repairable failure types
- hard failure signals
- replan budget behavior
- fingerprint rejection rules
- preview vs apply behavior

### Code Edit Kernel

Representative functions:

- _execute_code_edit_step
- _execute_multi_code_edit_step
- _apply_builtin_function_fix

Current rule:

Code edit is high-risk. Do not mix it with persistence/hydration extraction. It should remain stable until Code Chain/self-edit behavior is explicitly sealed.

Possible future extraction:

- core/tasks/scheduler_core/code_edit_kernel.py

Only extract after defining:

- rollback behavior
- atomic edit contract
- allowed target scope
- direct workspace edit policy
- verification handoff

## Phase10 Guardrails

Phase10 should not perform broad cleanup.

Allowed:

- Add boundary tests.
- Add architecture documentation.
- Add function inventory tests.
- Extract one kernel only after writing the ownership contract.
- Preserve passing test baseline after every change.

Not allowed:

- Mix planner and persistence changes in one commit.
- Mix repair and code edit changes in one commit.
- Delete functions only because they are small or look like wrappers.
- Move persistence/hydration logic without explicit resume/recovery tests.
- Change public task output shape without updating tests and checkpoint notes.

## Suggested Phase10 Sequence

### Step 1: Lock the current baseline

Record current scheduler size and test result.

Expected baseline after Phase9:

- scheduler.py: about 7234 lines
- Scheduler methods: about 155 defs
- Tests: 165 passed

### Step 2: Add boundary guardrail tests

Add tests that assert helper ownership remains outside scheduler.py:

- trace helpers are not reintroduced
- public task record helper exists
- dispatch wrappers are not reintroduced
- simple runner handlers are not reintroduced

### Step 3: Choose one kernel for design only

Recommended first kernel to design:

- Runtime Persistence Kernel

Reason:

Persistence and hydration are the deepest remaining scheduler ownership. They should be mapped before being moved.

### Step 4: Extract only after contract is stable

Do not extract persistence/hydration until a contract document and tests exist.

## Current Recommended Next Work Package

Phase10-A: Boundary Guardrails and Kernel Map

Scope:

- Add this document.
- Add or update tests that prevent old helper ownership from drifting back into scheduler.py.
- Do not move persistence/hydration/planner/repair/code-edit code yet.

Acceptance criteria:

- `python -m py_compile core/tasks/scheduler.py`
- `python -m pytest tests -q`
- Scheduler line/def count recorded.
- No functional behavior change.

## Notes for Future Development

The remaining scheduler size is not automatically bad.

At this stage, the key question is not:

"How many lines can be removed?"

The key question is:

"Which kernel owns which runtime responsibility?"

Only move code when the destination module has a stronger ownership claim than scheduler.py.
