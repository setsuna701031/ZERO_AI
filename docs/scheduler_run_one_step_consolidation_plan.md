# Scheduler run_one_step Consolidation Plan

## Status

This document is the canonical consolidation plan for `Scheduler.run_one_step`.

Current validated baseline:

- Full pytest: `5553 passed, 140 subtests passed`
- `compileall`: passed
- Active final implementation: `_zero_scheduler_run_one_step_v16`
- Current scope: analysis and consolidation planning only
- Do not modify `core/tasks/scheduler.py` until each wrapper side effect is mapped and covered.

## Current Problem

`core/tasks/scheduler.py` still contains a layered monkey-patch chain for `Scheduler.run_one_step`.

Current inventory shows:

- `25` run_one_step-related functions
- `23` `Scheduler.run_one_step` assignments
- `22` base captures
- Final active wrapper: `_zero_scheduler_run_one_step_v16`

The chain is currently passing tests, but it is high-risk technical debt because behavior depends on historical assignment order.

## Current Active Endpoint

```text
Scheduler.run_one_step = _zero_scheduler_run_one_step_v16
```

## Current Active Chain

```text
Scheduler.run_one_step original
  ↓
_zero_v734_run_one_step
  ↓
_zero_v352_scheduler_run_one_step
  ↓
_zero_v7332_scheduler_run_one_step
  ↓
_zero_v7333_scheduler_run_one_step
  ↓
_zero_v7334_scheduler_run_one_step
  ↓
_zero_v7335_scheduler_run_one_step
  ↓
_zero_v7336_scheduler_run_one_step
  ↓
_zero_scheduler_run_one_step_v1
  ↓
_zero_scheduler_run_one_step_v2
  ↓
_zero_scheduler_run_one_step_v3
  ↓
_zero_scheduler_run_one_step_v4
  ↓
_zero_scheduler_run_one_step_v5
  ↓
_zero_scheduler_run_one_step_v6
  ↓
_zero_scheduler_run_one_step_v7
  ↓
_zero_scheduler_run_one_step_v8
  ↓
_zero_scheduler_run_one_step_v9
  ↓
_zero_scheduler_run_one_step_v10
  ↓
_zero_scheduler_run_one_step_v11
  ↓
_zero_scheduler_run_one_step_v12
  ↓
_zero_scheduler_run_one_step_v13
  ↓
_zero_scheduler_run_one_step_v14
  ↓
_zero_scheduler_run_one_step_v15
  ↓
_zero_scheduler_run_one_step_v16
```

## Wrapper Responsibility Map

| Layer | Responsibility | Consolidation Action |
|---|---|---|
| Original `run_one_step` | Base scheduler execution route | Preserve as canonical base behavior |
| `_zero_v734_run_one_step` | Repair/retry landing | Move into canonical repair landing phase |
| `_zero_v352_scheduler_run_one_step` | Scheduler adapter payload and orchestration summary | Move into canonical orchestration enrichment phase |
| `_zero_v7332_scheduler_run_one_step` | Constitutional boundary metadata | Move into canonical metadata enrichment phase |
| `_zero_v7333_scheduler_run_one_step` | Governed continuation metadata | Move into canonical metadata enrichment phase |
| `_zero_v7334_scheduler_run_one_step` | Self-repair summary | Move into canonical metadata enrichment phase |
| `_zero_v7335_scheduler_run_one_step` | Controlled mutation bridge metadata | Move into canonical mutation metadata phase |
| `_zero_v7336_scheduler_run_one_step` | Verified mutation continuation metadata | Move into canonical mutation metadata phase |
| `_zero_scheduler_run_one_step_v1` | Runtime fallback, soft gate detection | Merge into canonical runtime fallback phase |
| `_zero_scheduler_run_one_step_v2` | Dispatch authority fallback | Merge into canonical runtime fallback phase |
| `_zero_scheduler_run_one_step_v3` | Granted execution authority fallback | Merge into canonical runtime fallback phase |
| `_zero_scheduler_run_one_step_v4` | Explicit authority fallback | Merge into canonical authority fallback phase |
| `_zero_scheduler_run_one_step_v5` | Explicit authority direct handler | Merge into canonical direct handler phase |
| `_zero_scheduler_run_one_step_v6` | Runtime gate result shape preservation | Merge into canonical result-shape phase |
| `_zero_scheduler_run_one_step_v7` | Operator session completion | Merge into canonical operator completion phase |
| `_zero_scheduler_run_one_step_v8` | Operator complete record | Merge into canonical operator completion phase |
| `_zero_scheduler_run_one_step_v9` | Forced operator completion | Merge into canonical operator completion phase |
| `_zero_scheduler_run_one_step_v10` | Forced operator completion updated logic | Merge into canonical operator completion phase |
| `_zero_scheduler_run_one_step_v11` | Operator completion helper | Merge into canonical operator completion phase |
| `_zero_scheduler_run_one_step_v12` | Terminal resume preservation | Merge into canonical resume lifecycle phase |
| `_zero_scheduler_run_one_step_v13` | Operator complete marker readback | Merge into canonical operator registry sync phase |
| `_zero_scheduler_run_one_step_v14` | Operator complete/failed marker readback | Merge into canonical operator registry sync phase |
| `_zero_scheduler_run_one_step_v15` | Failed step marker | Merge into canonical operator failure sync phase |
| `_zero_scheduler_run_one_step_v16` | Failed completion check | Merge into canonical operator failure sync phase |

## Target Mainline Shape

Future `Scheduler.run_one_step` should become a normal class method with explicit internal phases.

```text
run_one_step
  ↓
hydrate task
  ↓
terminal guard
  ↓
base execution route
  ↓
repair retry landing
  ↓
runtime / authority fallback handling
  ↓
direct handler handling
  ↓
metadata enrichment
  ↓
runtime result-shape preservation
  ↓
operator completion handling
  ↓
operator registry synchronization
  ↓
resume lifecycle preservation
  ↓
compact result
```

## Target Canonical Helper Functions

Introduce explicit helper functions before deleting wrappers:

```text
_canonical_repair_retry_landing
_canonical_orchestration_enrichment
_canonical_runtime_fallback
_canonical_authority_fallback
_canonical_direct_handler_dispatch
_canonical_runtime_result_shape
_canonical_operator_completion_recording
_canonical_operator_registry_synchronization
_canonical_resume_lifecycle_preservation
```

## Migration Rules

Do not delete wrapper layers blindly.

Each migration step must:

1. Move exactly one wrapper responsibility into a named Scheduler method or runtime/operator-owned helper.
2. Keep observable behavior identical.
3. Add or preserve focused tests for that behavior.
4. Remove only the replaced monkey assignment after tests prove equivalence.
5. Run the focused scheduler gate.
6. Run runtime resume/status gate.
7. Run full pytest before commit.
8. Commit only after green tests.

## Phase 1 Target

Create inventory-backed tests that lock down the current run_one_step responsibility chain before implementation changes.

Required coverage:

- final active implementation remains `_zero_scheduler_run_one_step_v16`
- each wrapper delegates to its captured base or equivalent base-like function
- v2 delegation through `_zero_scheduler_base_run_one_step_v2` is recognized as intentional
- runtime fallback behavior is preserved
- explicit authority fallback behavior is preserved
- direct handler behavior is preserved
- operator completion/failure registry behavior is preserved
- terminal resume lifecycle preservation is preserved

## Phase 2 Target

Introduce canonical helper functions while keeping the monkey-patch chain intact.

The first implementation step should be additive only:

- create helper
- call helper from existing wrapper
- prove tests remain green
- do not remove historical wrapper yet

## Phase 3 Target

Replace wrapper chain with canonical `run_one_step`.

Only after Phase 1 and Phase 2 are green:

- migrate wrapper behavior into canonical method order
- keep compatibility aliases only where needed
- remove historical monkey assignments in small batches
- run full test gate after each removal batch

## Required Test Gates

Focused scheduler gate:

```powershell
python -m pytest (Get-ChildItem tests -Filter "test_scheduler_*.py").FullName -q
```

Runtime resume/status gate:

```powershell
python -m pytest tests -q -k "resume or goal_lineage or persistent_queue"
```

Full gate:

```powershell
python -m pytest tests -q
python -m compileall core cli tests tools
```

## Non-Mainline Issue Reporting Rule

If consolidation discovers suspicious scheduler/runtime issues outside the current migration scope, report them explicitly.

Do not silently skip unrelated issues.
Do not hide non-mainline problems.
Do not mix unrelated fixes into the current migration commit.

Known non-mainline issue to track separately:

- ZERO runtime package execution previously violated forbidden write intent and overwrote `core/tasks/scheduler.py` during a report-only task. This must be fixed separately before ZERO can safely execute packages touching protected files.

## Immediate Next Step

Use this file as the canonical plan.

Recommended repository location:

```text
docs/scheduler_run_one_step_consolidation_plan.md
```

If another copy exists at:

```text
docs/architecture/scheduler_run_one_step_consolidation_plan.md
```

keep only one canonical copy or replace the architecture copy with a short pointer to this document.
