# ZERO Runtime v1 Release Candidate

Release candidate: `1.0.0-rc.1`  
Kernel version: `6.0.0`  
Runtime ABI: `1.0`  
Freeze manifest: `zero.runtime.freeze-manifest.v1`

## Architecture Freeze

ZERO Runtime v1 RC is a release-convergence bundle. Runtime behavior, authority ownership, persistence contracts, scheduler behavior, executor behavior, and activation boundaries are frozen. This bundle adds release documentation, validation tooling, a deterministic report, and a compatibility fixture only.

Post-freeze Runtime changes require contract review, invariant review, and compatibility review. Fixes are admissible only for a demonstrated long-validation defect, invariant failure, release-gate failure, documentation mismatch, or compatibility regression.

## Runtime Contracts

- Kernel descriptor: `zero.runtime.kernel`, kernel `6.0.0`, ABI `1.0`.
- Goal Runtime: `zero.agent.long_horizon_goal.v1`.
- Goal Daemon: `zero.agent.goal_daemon.v1`.
- Goal Operations: `zero.agent.goal_operations.v1`, projection `goal-operations-projection-v1`.
- Operator Dashboard: `zero.operator.dashboard.v1`, implementation `1.1`.
- Mission Runtime: `zero.runtime.mission.v1`.
- Approval flow: `zero.runtime.mission_execution_approval_flow.v1`.
- Event Bus: `zero.runtime.event_bus.v1`.
- Release report: `zero.runtime.release_report.v1`.

No persisted contract is upgraded or rewritten by this RC bundle.

## Supported Components

- Goal Runtime and persisted goal index
- Runtime Goal Controller
- Runtime Goal Daemon and fairness/recovery projections
- Goal Operations read surface
- Operator Dashboard v1.1
- Explicit Approval boundaries
- Mission Runtime and Mission sessions
- Activity Memory query surface
- Runtime Event Bus
- Focused Runtime release gate

## Release Gate

Run:

```text
python -m cli.zero_runtime_release_gate
```

The runner executes the focused Runtime invariant, Dashboard, Goal Runtime, Goal Operations, Daemon, Approval, and CLI suites. A candidate is releasable only when the command prints `PASS` and every Release Gate Summary row passes.

## Known Limitations

- Release readiness does not activate autonomous execution.
- Recovery execution remains disabled unless a future reviewed contract explicitly enables it.
- The Dashboard is a loopback-local HTTP operator surface; it is not a remote multi-user service.
- The RC gate is focused and intentionally does not run the complete repository test suite or multi-hour local validation.
- Performance values are functional baselines, not throughput or latency guarantees.

## Validation Scope

The RC validation scope covers Runtime invariants, Dashboard lifecycle and UI stability, Goal Runtime, Goal Operations, Daemon behavior, Approval boundaries, selected Mission Runtime flows, CLI contracts, deterministic release reporting, frozen-fixture integrity, and upgrade compatibility.

Long-running soak, platform matrices beyond the available Windows environment, full-repository pytest, production deployment, and activation validation remain local release-owner responsibilities.

## Upgrade Compatibility

`tests/fixtures/runtime_rc_v1/` is the immutable Runtime v1 RC compatibility source. Upgrade tests copy and read that fixture directly, verify its fixed SHA-256 manifest, exercise the current read surfaces, and prove byte invariance. Future Runtime upgrade coverage must use this fixture without modifying it.

## Deployment Notes

- Pin the Git commit recorded by `runtime_release_report.py`.
- Run the focused release gate from the repository root with the release Python environment.
- Verify the working tree contains no generated Runtime or Dashboard persistence.
- Preserve loopback-only Dashboard binding and existing security headers.
- Deployment must not infer activation, scheduler authority, executor authority, recovery authority, or mutation authority from RC status.
