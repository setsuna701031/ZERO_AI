# ZERO Repair Rollback Responsibility Mapping v1

Date: 2026-05-08  
Scope: prepare for safe rollback extraction after repair observability extraction.

## Goal

This document defines what may and may not be moved out of `task_runner.py` during a future rollback extraction.

This is not a code change plan yet. It is a safety boundary.

---

## 1. Current rollback responsibility

Rollback currently protects the repair runtime from leaving bad edits behind after failed verification.

The current flow is:

```text
repair apply / write
→ verify
→ verify failed
→ restore backup
→ persist rollback_result
→ mark failed / retry strategy
→ keep trace/audit evidence
```

This flow crosses several boundaries:

```text
StepExecutor        = performs file operations
TaskRunner          = coordinates repair/verify/rollback response
TaskRuntime         = persists runtime_state
FailurePolicy       = decides whether failure should quarantine / review / stop
repair_observability = formats repair trace and decision events
```

Because rollback crosses runtime state and file state, it is more dangerous than observability extraction.

---

## 2. What rollback helper may own

A future module may be:

```text
core/runtime/repair_rollback.py
```

It may own pure rollback helper behavior:

```text
- inspect rollback metadata
- determine backup path
- restore backup file
- build rollback_result payload
- normalize rollback error payload
- report restored_files / failed_files
```

Allowed functions:

```python
restore_repair_backup(...)
build_rollback_result(...)
is_rollback_available(...)
compact_rollback_error(...)
```

---

## 3. What rollback helper must NOT own

The rollback helper must not own lifecycle decisions.

Do not move these into `repair_rollback.py`:

```text
- mark task failed
- mark task finished
- choose strategy retry
- inject new repair steps
- call RepairPlanner
- call RepairStepInjector
- decide policy / quarantine
- modify scheduler queue
- decide current_step_index
- save runtime_state by itself unless explicitly passed a save callback later
```

Rollback helper should return a data payload.

TaskRunner should still decide what to do with that payload.

---

## 4. Current owner boundaries

### TaskRunner should keep

```text
- when rollback is called
- how rollback_result changes terminal status
- whether strategy retry happens after rollback
- when FailurePolicy.decide_repair is called
- how runtime_state is saved
- how repair session nodes are appended
- final public result shape
```

### repair_rollback.py may take

```text
- actual backup restore implementation
- missing backup handling
- file copy error normalization
- restored_files / failed_files calculation
- rollback_result shape
```

### TaskRuntime should keep

```text
- persistence
- execution log
- repair_context durability
- terminal state
```

### FailurePolicy should keep

```text
- rollback failure quarantine decision
- max repair depth
- recursive repair block
- critical path review requirement
```

---

## 5. Extraction risk

Rollback extraction is medium-high risk.

Risk areas:

```text
- backup path mismatch
- rollback_result shape changes
- existing tests expecting specific metadata
- failed verification becomes finished by mistake
- strategy retry bypasses quarantine
- missing backup is misclassified
```

---

## 6. Safe extraction order

### Step 1 — Add module only

Create:

```text
core/runtime/repair_rollback.py
```

Move only pure functions.

No behavior change.

### Step 2 — Keep TaskRunner as orchestrator

TaskRunner calls helper:

```python
rollback_result = restore_repair_backup(...)
```

But TaskRunner still persists and decides terminal status.

### Step 3 — Run focused tests

```powershell
python -m py_compile core/runtime/repair_rollback.py
python -m py_compile core/runtime/task_runner.py
python -m pytest tests/test_repair_chain_runtime.py -q -k "rollback"
python -m pytest tests/test_repair_chain_runtime.py -q -k "rollback or boundary or repair_policy or observability"
```

### Step 4 — Run smoke

```powershell
python app.py task run aer_auto_repair_injection_v2 --auto-repair
```

---

## 7. Acceptance criteria

Rollback extraction is accepted only if:

```text
- rollback tests still pass
- boundary tests still pass
- repair_policy tests still pass
- observability tests still pass
- auto repair smoke still finishes
- missing backup behavior remains stable
- successful rollback remains idempotent
- terminal failed task does not rerun rollback
```

---

## 8. Do not do in this extraction

Do not include:

```text
- new repair strategies
- scheduler changes
- policy rule expansion
- repo-scale rollback
- multi-worker locking
- target repo routing changes
- UI changes
```

---

## 9. Recommended next work package

Name:

```text
Repair Rollback Extraction v1
```

Files:

```text
core/runtime/task_runner.py
core/runtime/repair_rollback.py
tests/test_repair_chain_runtime.py
```

Goal:

```text
Move rollback restore helper logic out of task_runner.py while preserving TaskRunner orchestration.
```

Commit message:

```text
Extract repair rollback helpers
```
