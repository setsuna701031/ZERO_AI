# Phase10 Runtime Kernel Boundary Status

## Current phase

Phase10 is no longer a line-count cleanup phase.

It is the runtime kernel boundary design and verification phase.

The purpose is to protect the remaining scheduler kernel zones and prevent accidental extraction of core runtime logic.

---

## Current scheduler role

`core/tasks/scheduler.py` is now treated as the runtime orchestration kernel.

It still owns the following high-density kernel functions:

| Kernel zone | Function | Reason it stays in scheduler for now |
|---|---|---|
| Persistence kernel | `_persist_task_payload` | Durable task state writing and runtime recovery compatibility |
| Hydration kernel | `_hydrate_task_from_workspace` | Runtime state restoration and restart/resume behavior |
| Planner kernel | `_plan_goal` | Task intent to executable plan orchestration |
| Repair kernel | `_is_repairable_failure` | Repair/replan policy and failure classification |

These should not be moved as cleanup work.

---

## Already extracted ownership

The following responsibilities have already moved to helper/runtime layers:

| Responsibility | File |
|---|---|
| Trace support | `core/tasks/scheduler_core/trace_helpers.py` |
| Path resolution | `core/tasks/scheduler_core/step_path_helpers.py` |
| Simple runtime handlers | `core/tasks/scheduler_core/simple_runner_helpers.py` |
| Simple step execution | `core/tasks/scheduler_core/simple_step_executor_helpers.py` |
| Command-like step execution | `core/tasks/scheduler_core/command_step_helpers.py` |
| LLM step execution | `core/tasks/scheduler_core/llm_step_helpers.py` |
| Dispatch helpers | `core/tasks/scheduler_core/dispatch_helpers.py` |
| Queue synchronization | `core/tasks/scheduler_core/queue_sync_helpers.py` |
| Repo state helpers | `core/tasks/scheduler_core/repo_state_helpers.py` |
| Public task record adapter | `core/tasks/scheduler_core/public_task_record_helpers.py` |

---

## Phase10-B verification target

Phase10-B adds a boundary contract test:

```text
tests/test_runtime_kernel_boundary_contract.py
```

The test protects both sides of the boundary:

1. Scheduler must still keep the intentional kernel functions.
2. Scheduler must not reintroduce extracted wrapper ownership.
3. Extracted helper files must remain present.
4. Kernel boundary documents must remain present.

---

## Current rule

Do not measure Phase10 success by shrinking `scheduler.py`.

Measure Phase10 success by:

- stable test pass
- clear kernel ownership
- no wrapper ownership regression
- no accidental extraction of persistence/hydration/planner/repair kernels
- clean separation between scheduler kernel and scheduler_core helper layers

---

## Next safe direction

The next actual extraction should not happen until one kernel zone has dedicated behavior tests.

Recommended future design order:

1. Hydration kernel test design
2. Persistence kernel test design
3. Repair policy test design
4. Planner kernel test design

Only after that should a kernel extraction be attempted.
