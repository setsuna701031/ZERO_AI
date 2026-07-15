# ZERO Runtime v1 Freeze Manifest

Manifest version: `zero.runtime.freeze-manifest.v1`  
Release candidate: `1.0.0-rc.1`  
Freeze state: **Frozen**

| Runtime Core | Contract / Evidence | State |
| --- | --- | --- |
| Goal Runtime | `zero.agent.long_horizon_goal.v1` | Frozen |
| Goal Controller | `RuntimeGoalController` and existing transition contracts | Frozen |
| Goal Daemon | `zero.agent.goal_daemon.v1` | Frozen |
| Goal Operations | `zero.agent.goal_operations.v1` | Frozen |
| Operator Dashboard | `zero.operator.dashboard.v1`, Dashboard `1.1` | Frozen |
| Approval | Existing explicit approval and scope-fingerprint contracts | Frozen |
| Mission Runtime | `zero.runtime.mission.v1` and Mission session contracts | Frozen |
| Activity Memory | Existing activity-memory persistence/query contracts | Frozen |
| Event Bus | `zero.runtime.event_bus.v1` | Frozen |
| Release Gate | `cli.zero_runtime_release_gate` and Runtime invariant suite | Frozen |

## Required Review for Future Changes

Every future modification to a frozen component requires all three reviews before merge:

1. **Contract review** — proves public, persisted, authority, security, and error contracts remain compatible or are explicitly versioned.
2. **Invariant review** — proves ownership, byte invariance, deterministic projection, replay, TTL, budget, and zero-side-effect gates remain satisfied.
3. **Compatibility review** — runs the immutable `runtime_rc_v1` fixture directly and proves current readers do not rewrite it.

Absence of any review is a release-gate failure. RC status grants no activation, recovery, scheduler, executor, or mutation authority.

## Frozen Fixture Integrity

| Fixture file | SHA-256 |
| --- | --- |
| `goals/goal-index.json` | `e4f8d59c7ab65d77f3b00cc0329eb9d7f1cf78588ec56d1426bdda896716c381` |
| `goals/long-goal-9fef6559a936832b38e4/goal.json` | `e86ea0ea8bdcf7b5ac090c049d5f44656e2cf29ba61626daba144f6db565a8c1` |

The fixture is copied for tests and never repaired in place.
