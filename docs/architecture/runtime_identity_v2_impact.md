# Runtime Identity V2 Impact Analysis

## Current status

Goal Lineage, Queue Duplicate Identity, and Runtime Session Resume are currently connected through the same authority chain:

```text
extract_goal_lineage
→ canonical_work_identity
→ duplicate_identity
→ extract_queue_lineage
→ RuntimeSessionResume resume-plan dedupe
```

The current canonical work identity is:

```text
goal_lineage_id
session_id
runtime_session_id
branch_type
branch_id
```

This means queue duplicate detection is no longer based on `task_id` alone. It is scoped by goal lineage, session identity, runtime session identity, and branch identity.

## Current fallback behavior

`core/goals/goal_lineage_contract.py` currently allows `runtime_session_id` to be derived from `session_id`:

```python
runtime_session_id = _first(sources, "runtime_session_id") or session_id
```

Because of this fallback, `extract_goal_lineage(..., require_complete=True)` may still succeed when the original input does not explicitly contain `runtime_session_id`, as long as `session_id` exists.

`core/runtime/runtime_session_resume.py` also treats `session_id` and `runtime_session_id` as partially interchangeable when capturing task snapshots:

```python
"session_id": _first_text(
    task.get("session_id"),
    task.get("runtime_session_id"),
    metadata.get("session_id"),
    metadata.get("runtime_session_id"),
)
```

and:

```python
if not _first_text(session_task.get("session_id"), session_task.get("runtime_session_id")):
    session_task["session_id"] = normalized_session_id
```

This keeps Resume Seal V1 compatible, but it means Runtime Session Authority is not yet fully strict.

## Authority chain already sealed

The following areas are already connected to the current lineage authority path:

```text
Goal Lineage Contract
Goal Lineage Coordination Seal
Multi Session Coordination Seal
Persistent Queue Contract Seal
Persistent Queue Multi Session Seal
Runtime Session Resume Seal V1
Adaptive Planner Optional Lineage Support
Continuation Coordinator
Replan Coordinator
Adaptive Persistence Gateway
Decision Evidence
Evidence Authority
Evidence Repository
Goal Completion Authority
```

Current verified status before this document:

```text
Goal Lineage Coordination Seal      PASS
Multi Session Coordination Seal     PASS
Persistent Queue Contract Seal      PASS
Persistent Queue Multi Session      PASS
Runtime Session Resume Seal V1      PASS
compileall                          PASS
git diff --check                    PASS
git status                          CLEAN
```

## Risk

The current system guarantees:

```text
Goal Lineage Authority       sealed
Queue Duplicate Authority    sealed
Resume Authority V1          sealed
Runtime Session Authority    partial
```

The remaining gap is that `runtime_session_id` can be silently normalized from `session_id`.

This is not currently breaking tests, but it means the system cannot yet claim strict Runtime Identity Authority.

## Why Runtime Identity V2 should not be changed directly

Removing this fallback immediately would change the meaning of `extract_goal_lineage(..., require_complete=True)`.

For example, changing:

```python
runtime_session_id = _first(sources, "runtime_session_id") or session_id
```

to:

```python
runtime_session_id = _first(sources, "runtime_session_id")
```

would likely affect a wide blast radius:

```text
Goal Lineage Coordination Seal
Multi Session Coordination Seal
Persistent Queue Contract Seal
Persistent Queue Multi Session Seal
Runtime Session Resume Seal V1
Engineering Goal Loop
Adaptive Planner
Continuation Coordinator
Replan Coordinator
Adaptive Persistence Gateway
Decision Evidence
Evidence Authority
Evidence Repository
Goal Completion Authority
```

The audit showed that `session_id`, `runtime_session_id`, and related session lineage fields are referenced across many tests and runtime modules. Therefore, Runtime Identity V2 is not a safe one-line contract edit.

## Required next work

Before Runtime Identity V2 can be implemented, the project needs a Runtime Session Authority Inventory.

That inventory must answer:

```text
1. Who creates session_id?
2. Who creates runtime_session_id?
3. Which boundary owns runtime_session_id?
4. Which boundary may derive runtime_session_id from session_id?
5. Which boundary must reject missing runtime_session_id?
6. Which legacy paths still only provide session_id?
7. Should fallback remain compatibility behavior outside authority boundaries?
8. Should strict rejection apply only at sealed authority boundaries?
```

## Proposed Runtime Identity V2 direction

Runtime Identity V2 should be introduced as a staged migration, not a direct replacement.

Recommended direction:

```text
Stage 1:
Document current fallback and blast radius.

Stage 2:
Add Runtime Session Authority Inventory.

Stage 3:
Add explicit tests for runtime_session_id fallback behavior.

Stage 4:
Introduce strict boundary helper, for example:

    extract_runtime_identity(..., require_runtime_session=True)

Stage 5:
Apply strict mode only to authority boundaries first.

Stage 6:
Migrate legacy callers gradually.

Stage 7:
Only after all callers are migrated, remove fallback from canonical lineage extraction if still desired.
```

## Non-mainline issue found

During Goal Lineage / Queue / Resume authority audit, a non-mainline issue was found:

```text
runtime_session_id can be silently derived from session_id.
```

This is currently compatibility behavior, not a blocking bug.

However, it prevents the project from claiming full Runtime Identity Authority.

## Current decision

Do not modify `goal_lineage_contract.py` yet.

Do not remove the fallback yet.

Do not add a strict Runtime Identity V2 test until the Runtime Session Authority Inventory is complete.

The correct next engineering step is:

```text
Runtime Session Authority Inventory
```

not:

```text
Direct Runtime Identity V2 contract change
```
