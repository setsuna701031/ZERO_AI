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

---

## ZERO Engineering Runtime v3.3 - Governed Multi-Cycle Runtime Coordination

Implementation baseline: `b098fcd feat(engineering): add governed multi-cycle runtime coordination`.

Runtime v3.3 adds a governed orchestration layer, not a replacement artifact family. The model is:

```text
Engineering Runtime Session
├── Runtime Cycle 1: Proposal → Approval → Authorization → Execution → Verification → Feedback → Closure
├── Runtime Cycle 2: New Proposal → New Approval → New Authorization → Execution → Verification → Feedback → Closure
└── Runtime Cycle 3: New Proposal → New Approval → New Authorization → Execution → Verification → Completed/Closed
```

Architecture boundaries:

- Session identity and fingerprints are deterministic canonical JSON / SHA-256 seals.
- Cycle identity and fingerprints are deterministic canonical JSON / SHA-256 seals.
- Cycle 1 has no previous-cycle link; later cycles must reference the exact previous cycle identity and fingerprint.
- Cycle numbers cannot skip, repeat, or cross sessions.
- Each cycle must carry fresh Approval and Authorization references; prior-cycle Approval or Authorization references are rejected.
- Feedback can only create a Proposal Candidate marked candidate-only, not approved, not authorized, and not executable.
- Resume validates persisted session/cycle/checkpoint evidence and returns the next governed action; it never approves, authorizes, invokes adapters, runs shell commands, or executes mutations.
- Inspect is a read-only projection over existing session, cycle, journal, and checkpoint artifacts.
- Journal replay is deterministic because each entry has a strict sequence and previous-entry fingerprint chain.
- Checkpoints seal durable session state, current cycle references, journal head, verified artifact references, and resume metadata.

Therefore v3.3 remains governed coordination rather than a fully autonomous engineering loop. Actual repository mutation authority remains outside the Session coordinator and must continue through existing governed execution paths.

## Engineering Runtime v3.4 Objective and Completion Coordination

Runtime v3.4 is an additive governance layer over the v3.3 Engineering Runtime Session. The existing v3.3 Session/Cycle/Journal/Checkpoint/Resume/Inspect contracts remain frozen for required fields and fingerprint semantics; v3.4 persists additional artifacts in bounded session subdirectories.

The v3.4 artifact flow is: Session Objective → Cycle Objective Assignment → governed Proposal/Approval/Authorization/Execution/Verification/Feedback → Objective Progress Evaluation → Completion Readiness → Iteration Health → Iteration Decision. When readiness is sufficient, the runtime may create a Completion Review Request with `authority_state=not_granted`. A Human Completion Decision is separate from proposal approval and authorization; only `approved_complete` permits the existing completed-session transition.

Completion readiness fails closed when required acceptance criteria lack evidence, evidence references are invalid, lineage is invalid, scope deviates, a failed cycle remains open, unresolved feedback exists, or required objectives remain unsatisfied. Testing or verification success is treated as evidence only, not as automatic objective completion.

Iteration health uses deterministic progression deltas: newly satisfied criteria indicate progressing; new evidence without satisfaction indicates slow progress; three consecutive no-progress cycles indicate stalled; repeated verification failure identities indicate repeating failure. Stalled or repeating-failure health requires human reassessment and blocks unbounded next-candidate generation.

Next Iteration Objective Candidates are bounded by remaining approved objectives and criteria. They are explicitly candidate-only, not proposals, not approved, not authorized, and not executable.

## Engineering Work Entry v3.5 Architecture

The v3.5 work entry architecture provides a single coordination surface from `zero.engineering.work_request.v1` through `zero.engineering.work_intake.v1` into `zero.engineering.work_coordination.v1`. Coordination references the existing Engineering Runtime Session rather than creating a second runtime. Stage transitions are validated by artifact evidence: repository admission, repository analysis closure, objective, planning closure, proposal, proposal review closure, approval closure, authorization closure, execution preparation closure, execution result, verification closure, progress evaluation, completion review, or next-iteration handoff.

Inspection is read-only and reports stage timeline, missing artifacts, next governed action, authority state, runtime linkage, completion readiness, iteration health, and resumability. Resume revalidates the coordination artifact and returns a decision without planning automatic approval, authorization, execution, completion, or proposal creation. Persistence is under the session store `work-entry/` namespace using canonical UTF-8 JSON and read-back validation.

v3.5 is not a fully autonomous engineering loop. It is the governed entry and coordination layer that safely connects existing analysis, planning, proposal, review, approval, authorization, execution, verification, and v3.4 completion capabilities while preserving human governance gates.
