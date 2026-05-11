# Runtime Kernel Zones

## Purpose

This document defines the current kernel zones inside `core/tasks/scheduler.py`.

Phase8 and Phase9 reduced `scheduler.py` from a large mixed-responsibility runtime owner into a smaller orchestration/kernel file. At this point, the remaining high-density functions should not be treated as cleanup targets.

This document is a boundary map for Phase10 work.

---

## Current Kernel Spine

As of Phase10 baseline, the major remaining kernel functions are:

| Zone | Function | Current role |
|---|---|---|
| Repair Kernel | `_is_repairable_failure` | Decides whether a failed task may enter repair/replan flow |
| Hydration Kernel | `_hydrate_task_from_workspace` | Reconstructs task runtime state from persisted workspace files |
| Persistence Kernel | `_persist_task_payload` | Writes durable task payload/state back to disk/repository |
| Planner Kernel | `_plan_goal` | Converts user/task intent into executable task plan semantics |

These functions are not simple wrappers. They contain policy, state transition rules, recovery behavior, or semantic task orchestration.

---

## Zone 1: Repair Kernel

### Primary function

```text
_is_repairable_failure
```

### Responsibility

The repair kernel decides whether a failed task can safely enter repair or replan behavior.

It currently protects against unsafe or meaningless repair attempts, including:

- terminal or non-repairable task status
- replan budget exhaustion
- unsupported failed step types
- hard failures that should not be retried
- verify-step failure classification

### Boundary rule

Do not extract this as a generic helper unless the repair policy is separated into a dedicated repair-policy module.

### Allowed future direction

Possible future target:

```text
core/tasks/scheduler_core/repair_policy_helpers.py
```

Only move this when:

- repair policy has dedicated tests
- replan behavior remains unchanged
- failure classification stays deterministic
- no planner or persistence logic is mixed into the helper

---

## Zone 2: Hydration Kernel

### Primary function

```text
_hydrate_task_from_workspace
```

### Responsibility

The hydration kernel rebuilds task state from persisted task files and runtime state files.

It handles:

- loading planner result
- loading runtime state
- restoring steps/results/execution state
- preserving blocker/review state
- resuming eligible tasks after restart
- refreshing public task fields after hydration

### Boundary rule

Do not treat hydration as formatting or utility logic.

This is runtime recovery behavior.

### Allowed future direction

Possible future target:

```text
core/tasks/scheduler_core/task_hydration_runtime.py
```

Only move this when:

- persistence and hydration tests exist
- restart/resume behavior is covered
- blocker/review resume behavior is covered
- task state schema is documented
- public snapshot refresh is already separated

---

## Zone 3: Persistence Kernel

### Primary function

```text
_persist_task_payload
```

### Responsibility

The persistence kernel is responsible for durable task-state writing.

It protects the runtime by ensuring task payloads survive:

- scheduler restart
- task execution transition
- failure/retry transition
- queue rebuild
- runtime recovery

### Boundary rule

Do not extract this as a simple file helper.

Persistence is the durability boundary of the scheduler runtime.

### Allowed future direction

Possible future target:

```text
core/tasks/scheduler_core/task_persistence_runtime.py
```

Only move this when:

- file write behavior is fully covered
- runtime state write behavior is fully covered
- task snapshot compatibility is preserved
- rollback/failure behavior is understood
- no planner or repair policy enters persistence layer

---

## Zone 4: Planner Kernel

### Primary function

```text
_plan_goal
```

### Responsibility

The planner kernel converts task intent into executable plan semantics.

It currently coordinates or falls back across planning paths such as:

- deterministic task planning
- write/read/command planning
- document task planning
- inline step parsing
- fallback planner behavior
- task step normalization

### Boundary rule

Do not split planner logic casually.

Planner behavior is semantic orchestration, not utility formatting.

### Allowed future direction

Possible future target:

```text
core/tasks/scheduler_core/planner_kernel.py
```

Only move this when:

- planner entry contract is documented
- deterministic planner behavior is covered
- fallback behavior is covered
- document task planning is covered
- write/read/command planning tests exist
- no runtime persistence logic is mixed into planner layer

---

## Already Extracted Ownership

The following responsibilities have already moved out of scheduler ownership:

| Responsibility | Current layer |
|---|---|
| Trace helpers | `core/tasks/scheduler_core/trace_helpers.py` |
| Path helpers | `core/tasks/scheduler_core/step_path_helpers.py` |
| Simple runner helpers | `core/tasks/scheduler_core/simple_runner_helpers.py` |
| Simple step execution helpers | `core/tasks/scheduler_core/simple_step_executor_helpers.py` |
| Command step helpers | `core/tasks/scheduler_core/command_step_helpers.py` |
| LLM step helpers | `core/tasks/scheduler_core/llm_step_helpers.py` |
| Dispatch helpers | `core/tasks/scheduler_core/dispatch_helpers.py` |
| Queue sync helpers | `core/tasks/scheduler_core/queue_sync_helpers.py` |
| Repo state helpers | `core/tasks/scheduler_core/repo_state_helpers.py` |
| Public task record adapter | `core/tasks/scheduler_core/public_task_record_helpers.py` |

---

## Forbidden Phase10 Mistakes

Do not do the following in Phase10:

1. Do not continue deleting functions only because they are large.
2. Do not extract `_persist_task_payload` without persistence tests.
3. Do not extract `_hydrate_task_from_workspace` without restart/resume tests.
4. Do not extract `_plan_goal` without planner behavior tests.
5. Do not extract `_is_repairable_failure` without repair policy tests.
6. Do not mix planner, persistence, repair, and hydration into the same helper file.
7. Do not move core policy into display/UI/CLI layers.
8. Do not optimize line count at the cost of runtime ownership clarity.

---

## Phase10 Recommended Order

### Phase10-A: Boundary documents

Completed:

```text
docs/runtime_kernel_boundary_map.md
```

Current document:

```text
docs/runtime_kernel_zones.md
```

### Phase10-B: Kernel verification tests

Add tests that verify the remaining kernel functions exist and are intentionally owned by `scheduler.py`.

Suggested tests:

```text
tests/test_runtime_kernel_boundary_contract.py
```

Should check:

- `_persist_task_payload` remains in scheduler
- `_hydrate_task_from_workspace` remains in scheduler
- `_plan_goal` remains in scheduler
- `_is_repairable_failure` remains in scheduler
- extracted helper ownership remains outside scheduler

### Phase10-C: Pick one kernel for future extraction design

Do not extract immediately.

Choose one future direction:

1. Persistence kernel extraction design
2. Hydration kernel extraction design
3. Planner kernel extraction design
4. Repair policy extraction design

Recommended first future candidate:

```text
hydration kernel extraction design
```

Reason: hydration already has clearer runtime input/output shape than planner and repair policy.

---

## Current Architectural Interpretation

At this point, `scheduler.py` is no longer a general dumping ground.

It is becoming:

```text
runtime orchestration kernel
```

Its remaining responsibilities should be treated as kernel zones, not cleanup targets.

The goal of Phase10 is not to make the file smaller immediately.

The goal is to prevent architectural drift while preparing the next safe extraction boundary.
