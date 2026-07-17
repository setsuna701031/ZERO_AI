# System Architecture

The system is composed of five main layers:

1. Task Repository
2. DAG Scheduler
3. Scheduler Queue
4. Runtime State Machine
5. Task Runner

---

# Architecture Flow

Task Submit
↓
Task Repository
↓
DAG Scheduler
↓
Scheduler Queue
↓
Task Runner
↓
Runtime State Machine
↓
Task Finished / Failed / Retry / Replan

---

# Components

## Task Repository

Stores:

* task_id
* status
* depends_on
* history
* workspace_dir
* task_dir

## DAG Scheduler

Determines if a task is ready:

* All dependencies finished → queued
* Otherwise → blocked

## Scheduler Queue

Runnable task queue.

## Runtime State Machine

Tracks execution state and transitions:

* queued → running → finished
* running → retry
* running → failed
* running → replan

## Task Runner

Executes steps and updates runtime state.

---

# Goal Lineage Coordination Architecture

The runtime identity model now includes a canonical goal-lineage contract above
session identity and below evidence / authority / completion.

## Canonical Goal Scope

```text
root_goal_id
+ goal_lineage_id
+ session_id
+ runtime_session_id
```

This scope defines the goal lineage that queue, scheduler, resume, evidence,
authority, and completion must preserve.

## Canonical Child Identity

```text
goal_lineage_id
+ session_id
+ runtime_session_id
+ branch_type
+ branch_id
```

This identity is used for continuation / replan / child work-item isolation.
Only a fully matching child identity is duplicate-idempotent.

## Legacy Metadata

The following fields may still be preserved as metadata, but they are not enough
to prove runtime identity by themselves:

```text
task_id
package_id
goal_id
source_goal_id
continuation_id
replan_request_id
```

## Updated Coordination Flow

```text
Root Goal
↓
Goal Lineage Contract
↓
Continuation / Replan Coordinator
↓
Persistent Queue Contract
↓
Scheduler Queue
↓
Persistent Runtime Orchestrator
↓
Runtime Session Resume
↓
Decision Evidence
↓
Evidence Repository / Evidence Authority
↓
Goal Completion Authority
↓
Goal Finished / Failed / Retry / Replan / Resume
```

## Isolation Rules

```text
A resume cannot restore another root/session/lineage snapshot.
A retry cannot modify another branch identity.
A fail/finish transition is scoped to its canonical child identity.
A child finish cannot complete the wrong root goal.
Evidence must match the target goal lineage before completion authority accepts it.
Scheduler duplicate detection must use lineage-aware branch identity, not task_id alone.
```

## Ownership Boundaries

```text
Scheduler remains orchestration only.
Queue stores and deduplicates lineage-aware work items.
Resume restores lineage-matching snapshots only.
EvidenceRepository indexes and filters by lineage scope.
EvidenceAuthority validates lineage-scoped evidence chains.
GoalCompletionAuthority owns completion acceptance and rejects lineage mismatch.
```

## Validated Seal

```text
tests/test_goal_lineage_coordination_seal.py -> 6 passed
tests/test_multi_session_coordination_seal.py -> 8 passed
tests/test_persistent_queue_multi_session.py -> 2 passed
tests/test_persistent_queue_contract_seal.py -> 8 passed
python -m compileall core cli tests -> passed
git diff --check -> passed
```

Engineering verdict:

```text
Goal Lineage Coordination Seal: SEALED
```
