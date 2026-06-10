# AER Core Seal Snapshot

Seal date: 2026-06-09

## Purpose

This document is a point-in-time seal snapshot and regression evidence index.
It does not define a second runtime specification and does not add runtime or
adaptive behavior.

Canonical ownership and boundary rules remain in:

- `docs/runtime_state_schema.md`
- `docs/runtime_kernel_boundary_contract.md`
- `docs/kernel_surface_audit.md`

## Completed Core Capabilities

The following scoped capabilities are complete at this snapshot:

- Adaptive Planning Engine v1
- Runtime Terminal Metadata Consistency Seal
- Runtime State Ownership Seal for task/runtime/subgoal metadata synchronization
- `TaskRuntime` as the owner of runtime-state persistence, normalization, and
  synchronized task/runtime/subgoal terminal transitions
- Bounded deviation detection, retry/replan decisions, resume from the
  deviation point, and adaptive evidence-chain persistence
- Contract violations block instead of being automatically repaired or bypassed

This snapshot does not claim that the broader AER execution-authority,
mutation-authority, public API, or all lifecycle propagation surfaces are fully
sealed.

## Runtime State Ownership Rule

`TaskRuntime` is the state synchronization owner.

- `TaskRunner` executes and coordinates task steps through `TaskRuntime`.
- `TaskRuntime` persists and normalizes runtime state.
- Task status, runtime status, subgoal status, goal status, and repair-session
  terminal metadata must be synchronized through `TaskRuntime`.
- Scheduler and AgentLoop must not own adaptive decisions or directly mutate
  deep runtime-state fields.
- Completed execution records, `execution_log`, and evidence are preserved
  across deviation and resume transitions.

## Adaptive Planning Lifecycle

The sealed v1 lifecycle is:

```text
Plan
-> Execute
-> Observe
-> Detect Deviation
-> Decide Retry / Replan / Resume / Block
-> Resume from deviation point
-> Persist evidence chain
```

Adaptive planning uses the existing `TaskRunner` and `TaskRuntime`. It does not
create a parallel runtime. Contract violations are non-recoverable and must
transition to `blocked`.

## Terminal Metadata Consistency Rule

For tasks requiring terminal validation, `finished` is legal only after all of
the following are true:

1. Step execution succeeded.
2. Observation completed.
3. Artifact validation passed.
4. Evidence persistence completed.
5. No deviation report is active.

The legal runtime states added or sealed by this work are:

- `needs_observation`: execution completed, terminal observation/evidence seal pending
- `needs_resume`: a recoverable deviation requires execution to resume from the deviation point
- `recoverable`: recognized by persistent/runtime state routing as degraded but resumable
- `blocked`: an unrecoverable deviation, contract violation, or review/blocking condition prevents resume

If observation or artifact validation finds a deviation after apparent
completion, terminal metadata must not remain `finished`. `TaskRuntime`
synchronizes the task, runtime, subgoal, goal, and repair-session state to
`needs_resume` or `blocked` without clearing completed-step evidence or logs.

## Evidence Preservation Rule

- Adaptive evidence is append-only within the persisted runtime state.
- Original plan, deviation report, adaptive decision, revised plan, and resume
  result remain traceable.
- Completed-step `execution_log`, step results, and evidence must not be cleared
  when a terminal candidate is downgraded for resume.
- The existing untracked `runtime/evidence/` area was not modified by this seal.

## Regression Evidence

Recorded seal results:

| Pack | Result |
|---|---:|
| Terminal consistency regression | 5 passed |
| Adaptive tests | 9 passed |
| Runtime/state targeted regression | 33 passed |
| Full suite | 4601 passed, 186 subtests passed |

## Regression Commands

Terminal consistency regression:

```powershell
python -m pytest tests/test_runtime_terminal_metadata_consistency.py -q
```

Adaptive tests:

```powershell
python -m pytest tests/test_adaptive_deviation_detection.py tests/test_adaptive_replanning.py tests/test_adaptive_resume_execution.py tests/test_adaptive_evidence_chain.py -q
```

Runtime/state targeted regression:

```powershell
python -m pytest tests/test_task_runner_step_advance_persist.py tests/test_persistent_runtime_orchestrator_contract.py tests/test_runtime_session_resume_v1.py tests/test_runtime_session_resume_seal_v1.py tests/test_runtime_state_contract.py tests/test_runtime_state_normalization_v1.py tests/test_runtime_state_transition_normalization_v1.py tests/test_runtime_state_hygiene.py -q
```

Full suite:

```powershell
python -m pytest tests -q
```

## Hard Engineering Boundary

- Do not add a second runtime.
- Do not use force-resume, ignore-finished, terminal-bypass, or equivalent
  compatibility workarounds.
- Do not move adaptive decision logic into AgentLoop or Scheduler.
- Do not bypass existing runtime, authority, evidence, or mutation contracts.
- Fix contract drift at its owning layer instead of masking it with a
  compatibility layer.
- Preserve completed execution evidence and logs during recovery and resume.

## Non-Mainline Issue Reporting

Any issue outside the immediate task that can affect architecture, contracts,
state ownership, evidence integrity, or test stability must be reported. It
must not be silently ignored or represented as sealed.

## Known Documentation and Audit Drift

The following existing documents describe older or broader audit states and
are not silently rewritten by this snapshot:

- `docs/runtime_state_schema.md` does not yet list `needs_observation`,
  `needs_resume`, and `recoverable` in its status table.
- `docs/execution_authority_seal_matrix.md` still marks TaskRuntime lifecycle
  ownership as partially sealed because direct callers and broader execution
  authority remain audit concerns.
- `docs/aer_seal_audit.md` reports multiple lifecycle/status propagation owners.
  The current seal establishes TaskRuntime ownership for runtime-state
  synchronization; it does not resolve every broader lifecycle, recovery,
  replay, scheduler, or execution-authority ownership concern.

## Known Untouched Areas

- Untracked `runtime/evidence/` contents were not modified.
- Memory Layer work has not started under this seal.
- Long Horizon Goal work has not started under this seal.
- UI and operator-layer sealing is not included in this snapshot.
