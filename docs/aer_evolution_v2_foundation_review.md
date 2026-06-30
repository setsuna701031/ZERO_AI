# AER Evolution v2 Foundation Architecture Review

Package: 85 - AER v2 Foundation Architecture Review
Branch: `feature/aer-evolution-v2`
Baseline: `03d31dfa Add AER v2 resume engine`
Scope: documentation/review only. No runtime behavior was changed.

## Review Summary

The current v2 foundation is compact, importable, and acyclic across the reviewed modules:

- `core/runtime/aer_operator_lifecycle.py`
- `core/runtime/aer_operator_state_machine.py`
- `core/runtime/aer_operator_context.py`
- `core/runtime/aer_operator_checkpoint.py`
- `core/runtime/aer_operator_checkpoint_store.py`
- `core/runtime/aer_operator_resume.py`

The foundation does not import Scheduler or TaskRunner from the reviewed modules. Resume composes lifecycle, state-machine, context, checkpoint model, and checkpoint repository concerns without directly owning persistence or execution.

The main architecture issue is ownership clarity, not runtime correctness: transition rules are currently defined in lifecycle (`OPERATOR_ALLOWED_TRANSITIONS`, `can_transition_operator_phase`) and consumed/re-exposed by state machine (`can_transition`, `advance_operator_lifecycle`). This means the desired single source of truth, "State Machine owns transition rules," is not fully true yet. Lifecycle currently owns both phase definitions and transition table data.

## Ownership Table

| Responsibility | Current module | Review result |
| --- | --- | --- |
| Phase definitions | `aer_operator_lifecycle.py` | Owned by lifecycle via `OPERATOR_PHASES` and `OPERATOR_TERMINAL_PHASES`. No duplicate phase list found in the reviewed foundation. |
| Lifecycle record contract and validation | `aer_operator_lifecycle.py` | Owned by lifecycle. Validation also checks transition legality through lifecycle-local transition helpers. |
| Transition rules | `aer_operator_lifecycle.py` plus state-machine wrappers | Ownership is duplicated/blurred. Rule data lives in lifecycle, while state machine owns transition records and lifecycle advancement behavior. |
| Transition record contract/history | `aer_operator_state_machine.py` | Owned by state machine. No duplicate transition record schema found. |
| Shared runtime execution context | `aer_operator_context.py` | Owned by execution context. It validates phase membership only; it does not own transition rules. |
| Checkpoint schema and integrity | `aer_operator_checkpoint.py` | Owned by checkpoint model. It owns required fields, serialization/deserialization, and integrity hash validation. |
| Checkpoint persistence | `aer_operator_checkpoint_store.py` | Owned by checkpoint repository/store. It owns path resolution, atomic save, load, delete, list, and existence checks. |
| Resume composition | `aer_operator_resume.py` | Owned by resume. It loads through the repository, validates through the model, builds context, and uses the state machine to enter `resumed`. |

## Dependency Graph

Desired verification graph:

```text
Lifecycle
  |
  v
State Machine
  |
  v
Execution Context
  |
  v
Checkpoint Model
  |
  v
Checkpoint Repository
  |
  v
Resume Engine
```

Actual reviewed import graph:

```text
Lifecycle
  ^
  |
  +-- State Machine
  +-- Execution Context
  +-- Checkpoint Model

Checkpoint Model
  ^
  |
  +-- Checkpoint Repository

Checkpoint Model
Checkpoint Repository
Execution Context
Lifecycle
State Machine
  ^
  |
  +-- Resume Engine
```

Static import results:

| Module | Imports reviewed foundation modules |
| --- | --- |
| `aer_operator_lifecycle.py` | none |
| `aer_operator_state_machine.py` | `aer_operator_lifecycle` |
| `aer_operator_context.py` | `aer_operator_lifecycle` |
| `aer_operator_checkpoint.py` | `aer_operator_lifecycle` |
| `aer_operator_checkpoint_store.py` | `aer_operator_checkpoint` |
| `aer_operator_resume.py` | `aer_operator_checkpoint`, `aer_operator_checkpoint_store`, `aer_operator_context`, `aer_operator_lifecycle`, `aer_operator_state_machine` |

Review result:

- No circular imports were found.
- No reverse dependency from lifecycle into state machine/context/checkpoint/store/resume was found.
- No reverse dependency from checkpoint model into checkpoint store or resume was found.
- The actual graph does not match the requested linear chain. Context and checkpoint model depend directly on lifecycle instead of depending through state machine/context respectively. Resume imports multiple lower modules directly, which is reasonable for a composition layer but is not a strict single-edge chain.

## Single Source Of Truth Verification

| Claim | Result | Notes |
| --- | --- | --- |
| Lifecycle owns phase definitions. | Pass | `OPERATOR_PHASES` and terminal phase constants live in lifecycle. |
| State Machine owns transition rules. | Partial / issue | State-machine APIs enforce transitions, but the allowed transition table lives in lifecycle. |
| Execution Context owns shared runtime context. | Pass | Context schema/build/validate/copy/merge live in context module. |
| Checkpoint Model owns checkpoint schema. | Pass | Required fields, contract, stable serialization, and integrity hash logic live in checkpoint model. |
| Checkpoint Repository owns persistence. | Pass | File path safety, atomic writes, load/list/delete/existence live in checkpoint store. |
| Resume owns composition only. | Pass with note | Resume composes lower modules and does not perform direct file writes or import scheduler/runner. It does construct lifecycle/context records as part of composition. |

## Forbidden Import Review

| Rule | Result |
| --- | --- |
| Resume does not import Scheduler. | Pass |
| Resume does not import TaskRunner. | Pass |
| Checkpoint Store does not import Scheduler. | Pass |
| Checkpoint Model does not import Resume. | Pass |
| Execution Context does not own transition rules. | Pass |

The scoped scan of reviewed files found no imports or references to `core.tasks.scheduler`, `Scheduler`, `core.runtime.task_runner`, or `TaskRunner`.

## Circular Dependency Review

No circular imports were found among the reviewed foundation modules.

The current dependency shape is a fan-in toward lifecycle and a fan-out from resume:

- Lifecycle is the bottom primitive.
- State machine, context, and checkpoint model all consume lifecycle.
- Checkpoint store consumes checkpoint model.
- Resume consumes all lower foundation modules.

This is acyclic and stable for the current foundation. The main circularity risk for future work is allowing lifecycle to import state-machine helpers while state machine still imports lifecycle. That would immediately create a cycle.

## Foundation Findings

### FND-001: Transition rule ownership is split between lifecycle and state machine

Severity: non-critical architecture issue

`aer_operator_lifecycle.py` owns `OPERATOR_ALLOWED_TRANSITIONS` and `can_transition_operator_phase`, while `aer_operator_state_machine.py` owns `can_transition`, transition records, and lifecycle advancement. This violates the target statement that the State Machine owns transition rules.

Recommended future direction: move transition rule data and transition validation authority into the state-machine layer, while keeping lifecycle limited to phase definitions, terminal phase definitions, normalization, and lifecycle record shape. This should be done in a dedicated package because tests currently assert lifecycle transition helpers directly.

### FND-002: Actual dependency graph is acyclic but not the requested strict chain

Severity: deferred architecture alignment

The requested graph is linear, but the current implementation has direct imports from context and checkpoint model to lifecycle. This is not a correctness problem and may be acceptable because lifecycle phase definitions are primitive constants. It should still be documented as a difference from the requested graph.

Recommended future direction: decide whether the intended architecture is a strict layer chain or a primitive-contract graph. If strict layering is required, introduce narrower contract modules or route phase validation through explicit lower-level interfaces.

## Future Foundation Work

Deferred items only; no implementation was performed in this package.

- Clarify whether transition table ownership should move from lifecycle to state machine.
- Decide whether `can_transition_operator_phase` should remain as a compatibility helper, be deprecated, or be relocated.
- Decide whether context/checkpoint model direct imports from lifecycle are allowed as primitive phase-contract imports.
- Add an architecture test that asserts the approved import graph for the six foundation modules.
- Add an architecture test that blocks Scheduler/TaskRunner imports from resume/checkpoint foundation modules.
- Consider documenting resume as a composition root that is allowed to import all lower foundation modules.

## Non-Mainline Issues

- No critical correctness issue was found requiring changes to Scheduler, TaskRunner, Operator Loop, or Resume logic.
- The transition-rule ownership issue is non-mainline for this package because changing it would alter module APIs and tests. It is recorded for future foundation work only.
- The dependency graph mismatch is non-mainline for this package because the current graph is acyclic and the modules remain isolated from Scheduler/TaskRunner.

## Validation

Requested validation only:

```text
python tools/regression_runner.py fast
```

Result after run with bundled Python executable because `python` is not on PATH in this shell:

```text
370 passed, 5450 deselected, 73 subtests passed in 11.60s
```

No `compileall` and no full `pytest` were run.

## Git Diff Summary

Expected package diff:

- Add `docs/aer_evolution_v2_foundation_review.md`

## Git Status Short

Expected status after document creation:

```text
?? docs/aer_evolution_v2_foundation_review.md
```
