# Engineering Loop Governance Audit

## Decision

The Engineering Goal Loop is fail-closed at its direct governance boundaries.
Goal creation and transition now retain one canonical lineage; runner and loop
handoffs reject identity conflicts; completion still requires provenance-
validated evidence and canonical completion authority; resume retains the same
goal and session graph.

Audited flow:

```text
Engineering Goal Creation
  -> Goal State Transition
  -> Engineering Goal Runner
  -> Engineering Goal Loop
  -> Adaptive Continuation / Replan
  -> Runtime Governance Graph
  -> Evidence / Persistence / Resume
```

## Root-cause fixes

### Engineering goal persistence now preserves lineage

`EngineeringGoalRepository` previously normalized records through
`EngineeringGoal.from_mapping().as_dict()` without retaining lineage fields.
Creation, reload, or transition could therefore lose the identity graph and let
the runner mint a replacement later. Records now receive canonical root lineage
at creation, persist all lineage fields, retain them across transition, and
reject top-level or embedded metadata/payload conflicts.

Invalid sentinel identities (`unknown`, `default`, `legacy`, `runtime`, and
`system`) are rejected at this boundary.

### Runner and loop conflicts now fail closed

`EngineeringGoalRunner` compares persisted and requested lineage before runtime
handoff, validates any governance identity returned by runtime, and attaches the
canonical lineage to its result. `EngineeringGoalLoop` uses persisted lineage,
rejects explicit session overrides that disagree with it, always passes lineage
to the runner, and rejects conflicting runner output.

The old signature-based call that silently invoked a runner without
`goal_lineage` was removed.

### Corrupt persistence is no longer converted to an empty repository

Malformed JSON, invalid repository shape, and invalid individual goal records
now raise explicit errors. They can no longer masquerade as a missing goal.

## Verified closures

`tests/test_engineering_loop_governance_audit.py` verifies:

- Engineering Goal Lineage Closure
- Engineering Session Closure
- Goal Transition Governance Closure
- Goal Completion Evidence Closure
- Engineering Runner Governance Closure
- Engineering Loop Governance Closure
- Continuation Governance Closure
- Replan Governance Closure
- Resume Governance Closure
- No Direct Runtime Authority Mint
- No Direct Runtime Capability Mint
- No Direct Mutation Path
- No Direct Persistence Path
- No Quiet Success on Governance Conflict
- No Legacy Engineering Bypass at the loop/runner boundary

The loop delegates adaptive persistence through `AdaptivePersistenceGateway`;
it does not call repository save/update or filesystem write methods directly.
The runner delegates execution and does not mint runtime authority or capability.

## Non-mainline findings

The following remain visible even when the audit tests pass:

1. `core/tasks/engineering_goal_work_package_mainline.py` is an active,
   specialized pre-orchestrator route used by `EngineeringGoalRunner` for
   workspace-file goals. It uses `Planner`, `WorkPackageScheduler`, validated
   evidence, and `GoalCompletionAuthority`, but this audit does not prove that
   it carries every authority/capability/ownership/mutation/persistence record
   in the newer Runtime Governance Graph. It must remain a convergence target;
   it is not silently classified as fully sealed.
2. `core/tasks/goal_continuation_coordinator.py` transitively invokes
   `core.tasks.engineering_task_runner.run_engineering_task`. That path sits
   below `EngineeringRuntimeOrchestrator` and is outside the direct loop/runner
   mutation scope changed here. Its eventual convergence on the sealed runtime
   dispatcher remains a separate runtime-routing finding.
3. `RuntimeSessionResume` still contains an explicit legacy migration path for
   records without a V2 runtime identity graph. Such records are blocked when
   canonical lineage is missing, so the path is not quiet success, but it is not
   equivalent to a fully sealed resume graph and remains inventory.
4. Scheduler-core contains compatibility and legacy-detection helpers. No
   direct EngineeringGoalLoop import of those helpers was found; this audit does
   not claim they are retired.

No parallel `EngineeringGoalLoop` class or archive-candidate import was found in
the audited direct boundary. No hidden completion path was accepted: terminal
success continues to require an issued `GoalCompletionResult` backed by
provenance-validated evidence.

## Validation

```text
pytest -q tests/test_engineering_loop_governance_audit.py
pytest -q tests/test_adaptive_governance_audit.py
pytest -q tests/test_runtime_governance_final_audit.py tests/test_runtime_governance_graph_closure.py tests/test_runtime_mutation_closure.py tests/test_runtime_ownership_closure.py tests/test_runtime_persistence_closure.py tests/test_runtime_evidence_closure.py tests/test_runtime_identity_closure.py tests/test_runtime_capability_propagation_closure.py tests/test_runtime_authority_source_closure.py tests/test_runtime_execution_capability_unification_audit.py
python -m compileall core/runtime core/evidence core/goals core/tasks core/session core/adaptive tests
git diff --check
```
