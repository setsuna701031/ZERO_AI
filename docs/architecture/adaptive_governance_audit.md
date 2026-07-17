# Adaptive Planning Governance Audit

## Decision

The audited adaptive path remains subordinate to the sealed runtime governance
graph. Continuation and replan may create a new lineage branch, but they may not
mint a second authority, identity, ownership, mutation, goal, or session root.

Canonical flow:

```text
Adaptive Planning
  -> Continuation or Replan
  -> Engineering Goal Loop
  -> Runtime Governance
```

## Scope

The audit starts at `core/adaptive/` and follows the active engineering-goal
handoff through these files:

- `core/adaptive/continuation_runtime.py`
- `core/adaptive/continuation_coordinator.py`
- `core/adaptive/replan_runtime.py`
- `core/adaptive/replan_coordinator.py`
- `core/tasks/engineering_goal_loop.py`
- `core/tasks/engineering_goal_runner.py`

Archive candidates, documentation, test fixtures, and unrelated adaptive
experiments are outside the executable-path assertion. They remain visible as
inventory and are not evidence that the audited mainline is clean.

## Enforced invariants

1. **No adaptive authority bypass.** Adaptive runtime and coordinator modules
   cannot import runtime authority or capability implementations directly.
2. **No adaptive identity bypass.** Identity is accepted or derived through
   `core.goals.goal_lineage_contract`; adaptive modules cannot synthesize local
   session-ID conventions.
3. **No adaptive ownership bypass.** Adaptive modules cannot bind directly to a
   runtime ownership implementation or create an alternate owner graph.
4. **No adaptive mutation bypass.** Bookkeeping state replacement requires each
   runtime's private mutation authority. Adaptive modules cannot bind directly
   to governed mutation implementations.
5. **No continuation graph fork.** A continuation receives an explicit new
   branch ID/type while preserving lineage ID, root goal, source goal, session,
   and runtime session.
6. **No replan graph fork.** A replan receives an explicit new branch ID/type
   while preserving lineage ID, root goal, source goal, current goal, session,
   and runtime session.
7. **No goal-lineage drift.** Branch construction uses the canonical lineage
   contract and rejects conflicting identity input.
8. **No session drift.** Both session identifiers survive continuation and
   replan unchanged.

The executable proof is `tests/test_adaptive_governance_audit.py`.

## Mainline topology

- `EngineeringGoalRunner` is the only audited entry that imports
  `EngineeringAdaptivePlanner`. This is the canonical planning decision point,
  not a parallel planner.
- `EngineeringGoalLoop` delegates continuation creation to
  `ContinuationCoordinator` and replan record creation to `ReplanCoordinator`.
- `ContinuationRuntime` and `ReplanRuntime` are bounded bookkeeping objects. They
  do not execute tasks, grant authority, assign ownership, or invoke mutation
  gateways.
- Coordinators construct canonical lineage branches; they do not replace the
  governance root.

## Mandatory non-mainline reporting

The audit fails and prints every in-scope finding when it detects:

- a parallel or alternate adaptive planner marker;
- a legacy continuation or replan marker;
- a direct adaptive authority, capability, ownership, or mutation import;
- locally synthesized adaptive session identity;
- continuation or replan root, goal, lineage, or session drift.

Current in-scope findings: **none**.

This result does not claim that similarly named modules elsewhere in the
repository are retired or safe. Passing tests are evidence for the six-file
mainline above only; compatibility code and archive candidates must not be
silently omitted from broader runtime inventory work.

## Verification

```text
pytest -q tests/test_adaptive_governance_audit.py
pytest -q tests/test_continuation_runtime.py tests/test_continuation_coordinator.py tests/test_replan_runtime.py tests/test_replan_coordinator.py tests/test_engineering_goal_loop.py tests/test_engineering_goal_runner.py tests/test_engineering_goal_loop_continuation_replan_split.py tests/test_engineering_goal_loop_responsibility_split.py
```
