# Scheduler run_one_step Consolidation Plan

## Goal

Consolidate the active Scheduler.run_one_step wrapper chain into a canonical run_one_step path without changing observable runtime behavior.

## Current active endpoint

Scheduler.run_one_step = _zero_scheduler_run_one_step_v16

## Active wrapper responsibility map

| Layer | Responsibility | Action |
|---|---|---|
| _zero_v734_run_one_step | repair/retry landing | preserve |
| _zero_v352_scheduler_run_one_step | orchestration summary attachment | preserve |
| _zero_v7332_scheduler_run_one_step | constitutional boundary marker | preserve |
| _zero_v7333_scheduler_run_one_step | governed continuation attachment | preserve |
| _zero_v7334_scheduler_run_one_step | self repair summary | preserve |
| _zero_v7335_scheduler_run_one_step | controlled mutation bridge | preserve |
| _zero_v7336_scheduler_run_one_step | verified mutation continuation | preserve |
| _zero_scheduler_run_one_step_v1-v5 | runtime fallback authority path | merge into canonical fallback layer |
| _zero_scheduler_run_one_step_v6-v11 | step index and operator completion bookkeeping | merge into canonical completion layer |
| _zero_scheduler_run_one_step_v12-v16 | operator registry completion/failure integration | merge into canonical operator registry layer |

## Consolidation rules

1. Do not delete wrappers before equivalent behavior is covered by tests.
2. Preserve final observable behavior before removing historical layers.
3. Keep Scheduler as orchestration entrypoint only.
4. Move operator registry mutation toward runtime/operator-owned helpers.
5. Any non-mainline issue discovered during consolidation must be reported explicitly, not silently skipped.

## Phase 1 target

Create inventory-backed tests that lock down the current run_one_step responsibility chain before implementation changes.

## Phase 2 target

Introduce canonical helper functions:
- canonical repair retry landing
- canonical orchestration enrichment
- canonical runtime fallback
- canonical step index advancement
- canonical operator completion recording
- canonical operator registry synchronization

## Phase 3 target

Replace wrapper chain with canonical run_one_step and keep compatibility aliases only as needed.

## Validation baseline

Last known full test result:

5527 passed
140 subtests passed
0 failed
