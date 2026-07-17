# Runtime Authority Matrix v1

This audit defines the runtime authority boundaries for the AER engineering loop.
It is an authority map, not a feature layer.

## Authority owners

| Domain | Legal owner | May execute runtime | May persist goal | May write evidence | May write memory |
|---|---|---:|---:|---:|---:|
| Engineering session bookkeeping | `EngineeringSessionRuntime` + `SessionProgressionCoordinator` | No | No | No | No |
| Continuation bookkeeping | `ContinuationRuntime` | No | No | No | No |
| Continuation work item creation | `ContinuationCoordinator` | No | Yes, only continuation goal via injected repository | No | No |
| Replan bookkeeping | `ReplanRuntime` | No | No | No | No |
| Replan record creation | `ReplanCoordinator` | No | No | No | No |
| Loop decision dispatch | `GoalLoopDispatcher` | No | No | No | No |
| Terminal result assembly | `GoalLoopTerminalCoordinator` | No | No | No | No |
| Adaptive persistence | `AdaptivePersistenceGateway` | No | metadata only through repository boundary | decision evidence through EvidenceAuthority | No |

## Prohibited paths

- `EngineeringGoalLoop` must not own continuation creation.
- `EngineeringGoalLoop` must not own replan creation.
- `ContinuationRuntime` must not call `save_goal`, `update_goal`, or write evidence.
- `ReplanRuntime` must not create replan records by itself.
- `GoalLoopDispatcher` must not mutate runtime internals directly; it only receives and returns runtime contracts.
- `GoalLoopTerminalCoordinator` must not persist records, write evidence, mutate runtime, or write memory.
- Session runtime, continuation runtime, and replan runtime must stay bookkeeping-only.

## Known follow-up risk

`EngineeringSessionRuntime`, `ContinuationRuntime`, and `ReplanRuntime` all carry related counters. Current authority is safe because continuation and replan counters are sourced from their dedicated runtimes and mirrored into session runtime. A later audit should verify single-source-of-truth rules before long-chain memory or multi-session resumption expands this path.
