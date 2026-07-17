# Runtime Single Source Of Truth Matrix v1

This audit defines the single source of truth for bounded engineering runtime state.

## Rule

One state must have one owner, one write path, and one authority boundary.

## Ownership Matrix

| State | Owner | Write Path | Mirrors Allowed | Notes |
| --- | --- | --- | --- | --- |
| `current_goal_id` | `ContinuationRuntime` | `ContinuationCoordinator -> ContinuationRuntime.record_work_item()` | `EngineeringSessionRuntime.current_goal_id` may mirror only after dispatcher result | Continuation is the only layer that advances to a continuation goal. |
| `continuation_count` | `ContinuationRuntime` | `ContinuationRuntime.record_work_item()` | `EngineeringSessionRuntime.continuation_count` may mirror only from `ContinuationRuntime` | Session runtime must not independently increment continuation count. |
| `replan_count` | `ReplanRuntime` | `ReplanRuntime.record_replan()` | `EngineeringSessionRuntime.replan_count` may mirror only from `ReplanRuntime` | Session runtime must not independently increment replan count. |

## Forbidden Paths

- `EngineeringSessionRuntime` must not create continuation work items.
- `EngineeringSessionRuntime` must not create replan records.
- `EngineeringSessionRuntime` must not be treated as the write owner for `continuation_count` or `replan_count`.
- `GoalLoopDispatcher` must not mutate runtime counters directly; it must return updated runtime objects produced by the proper coordinator.
- `GoalLoopTerminalCoordinator` must not reconcile or overwrite runtime counters.

## Drift Protection

A drift exists when mirrored runtime state disagrees with the authoritative runtime:

- `EngineeringSessionRuntime.current_goal_id != ContinuationRuntime.current_goal_id`
- `EngineeringSessionRuntime.continuation_count != ContinuationRuntime.continuation_count`
- `EngineeringSessionRuntime.replan_count != ReplanRuntime.replan_count`

Such drift must be detectable and must not be silently accepted.

## Seal Condition

Runtime Authority Audit v2 is sealed only when tests prove:

1. `current_goal_id` has a single owner.
2. `continuation_count` has a single owner.
3. `replan_count` has a single owner.
4. drift between mirrors and owners is detectable.
5. terminal assembly does not hide or repair runtime drift.
