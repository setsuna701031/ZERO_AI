# ZERO Runtime Responsibility Mapping v1

Date: 2026-05-08  
Scope: architecture stabilization before scheduler / task_runner slimming.

## Current status

The repair runtime line is now stable enough to pause feature expansion:

- Auto repair runtime loop is working.
- Rollback safety targeted tests passed.
- Boundary tests passed.
- Repair policy layer targeted tests passed.
- Repair observability targeted tests passed.
- Final smoke passed with 11 targeted tests.

This document is not a refactor plan yet. It is a responsibility map to prevent unsafe file splitting.

---

## 1. `core/tasks/scheduler.py`

### Current role

`scheduler.py` is the outer orchestration layer.

It should own:

- task discovery
- queue rebuild
- repo/task registry sync
- worker dispatch
- task hydration from workspace
- dependency unblock
- ready/running/terminal state handoff
- dispatch gate / review gate
- task-level lifecycle transitions

### Responsibilities currently living here

#### A. Queue and worker orchestration

Belongs here.

- rebuild ready queue
- dispatch tasks to worker pool
- cancel invalid ready tasks
- avoid dispatching blocked/review/terminal tasks
- handle missing repo tasks
- requeue ready tasks after runtime result

Keep in scheduler.

#### B. Repo/task registry sync

Mostly belongs here.

- source of truth: `workspace/tasks.json`
- hydrate task from `workspace/tasks/<task_id>/runtime_state.json`
- sync runtime back to repo
- orphan task registration support from CLI path

Keep in scheduler/app boundary. Do not move into TaskRunner.

#### C. Dispatch gate / review gate

Belongs here as a scheduler-level safety check.

- block `review_required`
- block `waiting`
- block active blockers
- skip terminal tasks

Keep in scheduler, but later may move helper logic to:

```text
core/tasks/scheduler_core/runtime_dispatch_gate.py
```

#### D. Repair enqueue / repair fingerprint

Partially belongs here.

Scheduler may suppress duplicate repair task creation because that is queue-level behavior.

However, repair *decision* should not live here long-term.

Future split candidate:

```text
core/runtime/repair_policy.py
core/runtime/repair_fingerprint.py
```

#### E. Simple task execution helpers

Should not grow further inside scheduler.

Current risk:

```text
scheduler.py is accumulating execution details that belong to TaskRunner / StepExecutor.
```

Future split candidates:

```text
core/tasks/scheduler_core/simple_task_adapter.py
core/tasks/scheduler_core/queue_hydration.py
core/tasks/scheduler_core/dispatch_gate.py
```

### What should NOT be added to scheduler anymore

Do not add:

- repair synthesis rules
- rollback file restore logic
- code patch application
- step execution details
- repair policy rules
- observability event formatting beyond dispatch-level trace
- target repo edit logic

---

## 2. `core/runtime/task_runner.py`

### Current role

`task_runner.py` is the inner runtime execution loop.

It should own:

- one task's step-by-step execution
- runtime state load/save coordination
- step execution handoff
- terminal result handling
- repair orchestration at runtime level
- rollback response
- policy decision application
- observability emission for repair decisions

### Responsibilities currently living here

#### A. Runtime tick loop

Belongs here.

- load runtime state
- check terminal/waiting state
- run bounded auto ticks
- stop on terminal/block/wait/review
- avoid infinite execution loops

Keep in TaskRunner.

#### B. Step execution handoff

Belongs here only as orchestration.

TaskRunner may call StepExecutor, but should not duplicate StepExecutor behavior.

Keep:

```text
prepare context -> execute_step -> normalize result -> persist result
```

Avoid adding:

```text
new file operation implementations
new command execution rules
new patch application internals
```

Those belong to StepExecutor / step handlers.

#### C. Repair orchestration

Currently belongs here, but should be carefully separated later.

TaskRunner may coordinate:

```text
failure observed
→ repair policy decision
→ repair planner
→ repair injector
→ runtime state injection
→ verify
→ rollback if needed
```

But detailed rules should live elsewhere:

```text
RepairPlanner: how to synthesize repair candidate
RepairStepInjector: how to convert repair plan to steps
FailurePolicy / RepairPolicy: whether repair is allowed
TaskRuntime: how to persist state
StepExecutor: how to execute steps
```

#### D. Rollback handling

Currently acceptable here because rollback is tied to runtime repair execution.

Future split candidate:

```text
core/runtime/repair_rollback.py
```

Move only after stability remains good.

#### E. Repair observability

Belongs partially here.

TaskRunner should emit repair decision events because it sees:

- failed step
- repair policy decision
- repair injection
- rollback
- terminal result

But formatting and compaction may later move to:

```text
core/runtime/repair_observability.py
```

#### F. Policy decision application

TaskRunner may call policy and apply the result.

But actual policy rules should remain outside TaskRunner.

Keep policy in:

```text
core/runtime/failure_policy.py
```

Future rename candidate:

```text
core/runtime/repair_policy.py
```

Only rename later, not now.

---

## 3. `core/runtime/failure_policy.py`

### Current role

Policy table and repair decision gate.

Current responsibilities:

- generic failure decision
- repair recursion blocking
- max repair depth
- rollback hard-fail quarantine
- critical repo path review requirement
- normal sandbox repair allow

This file is small and currently good.

### Future risk

The file name is starting to blur two concepts:

```text
failure policy
repair policy
```

Do not rename now.

Later split candidate:

```text
core/runtime/failure_policy.py
core/runtime/repair_policy.py
```

Trigger for split:

- repair policy grows beyond ~150-200 lines
- repo risk matrix grows
- review/quarantine policy expands
- policy starts needing external config

---

## 4. `core/runtime/repair_planner.py`

### Current role

Repair candidate synthesis.

Should own:

- interpreting failed result
- classifying repair type
- proposing repair action
- producing repair plan

Should not own:

- step injection
- runtime persistence
- queue dispatch
- rollback
- policy permission

---

## 5. `core/runtime/repair_step_injector.py`

### Current role

Convert repair plan into normal runtime steps.

Should own:

- repair plan -> write_file / run_python / verify steps
- step metadata
- injection structure

Should not own:

- deciding whether repair is allowed
- executing steps
- saving runtime state
- rollback file restore

---

## 6. `core/runtime/task_runtime.py`

### Current role

Persistence and runtime state ownership.

Should own:

- runtime_state load/save
- current_step_index
- execution_log
- results
- terminal state
- repair_context persistence
- engineering_session / goal_state persistence

Should not own:

- repair synthesis
- queue dispatch
- command execution
- repo risk policy

Critical rule preserved:

```text
runtime_state.steps is source of truth after dynamic repair injection.
Do not let task.steps overwrite injected runtime steps.
```

---

## 7. `core/runtime/step_executor.py` and `step_handlers.py`

### Current role

Actual step implementation.

Should own:

- run_python behavior
- write_file behavior
- apply_patch behavior
- verify behavior
- command execution guard integration
- file operation details

Should not own:

- scheduler queue
- repair policy
- repair strategy switching
- task lifecycle

---

## 8. Immediate architecture risks

### Risk 1: `task_runner.py` becomes another scheduler

Symptoms:

- queue logic appears in TaskRunner
- repo registry appears in TaskRunner
- dispatch gate appears in TaskRunner

Action:

```text
Do not add queue/repo-discovery behavior to task_runner.py.
```

### Risk 2: `scheduler.py` becomes another runtime

Symptoms:

- repair synthesis inside scheduler
- rollback file restore inside scheduler
- step execution details inside scheduler

Action:

```text
Do not add repair execution details to scheduler.py.
```

### Risk 3: policy rules spread across files

Symptoms:

- critical path checks duplicated
- repair depth checked in scheduler and task_runner
- rollback quarantine checked in multiple places

Action:

```text
Keep policy decision in FailurePolicy.decide_repair for now.
```

### Risk 4: observability becomes noisy and unusable

Symptoms:

- full runtime_state dumped into trace
- repeated giant payloads
- no compact chain id / reason

Action:

```text
Keep trace compact.
Record decision/reason/chain id, not full nested objects.
```

---

## 9. Safe refactor order

Do not split everything at once.

Recommended order:

### Step 1 — Freeze behavior

Already mostly done.

Run before every split:

```powershell
python -m py_compile app.py
python -m py_compile core/runtime/failure_policy.py
python -m py_compile core/runtime/task_runner.py
python -m py_compile core/runtime/task_runtime.py
python -m py_compile core/runtime/repair_planner.py
python -m py_compile core/runtime/repair_step_injector.py
python -m py_compile core/tasks/scheduler.py
python app.py task run aer_auto_repair_injection_v2 --auto-repair
python -m pytest tests/test_repair_chain_runtime.py -q -k "rollback or boundary or repair_policy or observability"
```

### Step 2 — Extract pure helpers only

First safe extraction candidates:

```text
task_runner.py -> core/runtime/repair_observability.py
task_runner.py -> core/runtime/repair_rollback.py
scheduler.py -> core/tasks/scheduler_core/runtime_dispatch_gate.py
scheduler.py -> core/tasks/scheduler_core/queue_hydration.py
```

Do not extract behavior-changing logic first.

### Step 3 — One extraction per commit

Each commit should move one responsibility only.

Example:

```text
Extract repair observability helpers
```

Then run smoke.

### Step 4 — Avoid touching planner/scheduler/task_runner together

High-risk combination:

```text
scheduler.py + task_runner.py + task_runtime.py
```

Avoid changing all three in one refactor commit unless fixing a verified integration bug.

---

## 10. Recommended next work package

### Work package name

```text
Runtime Repair Observability Extraction v1
```

### Scope

Only extract compact event/decision formatting from `task_runner.py`.

### Files

```text
core/runtime/task_runner.py
core/runtime/repair_observability.py
tests/test_repair_chain_runtime.py
```

### Acceptance

```powershell
python -m py_compile core/runtime/task_runner.py
python -m py_compile core/runtime/repair_observability.py
python -m py_compile tests/test_repair_chain_runtime.py
python -m pytest tests/test_repair_chain_runtime.py -q -k "observability"
python -m pytest tests/test_repair_chain_runtime.py -q -k "rollback or boundary or repair_policy or observability"
```

### Do not do yet

Do not split scheduler yet.

Scheduler split should wait until one runtime extraction succeeds.
