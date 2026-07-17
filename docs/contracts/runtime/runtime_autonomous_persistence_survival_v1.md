# Runtime Autonomous Persistence Survival Contract v1

## Scope

Package 1673-1696 adds a survivable autonomous runtime data layer for process stop, crash, or restart.

This layer persists and reloads checkpoint records only. It does not perform work, invoke dispatch paths, mutate progress state, advance cursors, or create an unbounded loop.

## Records

### Runtime loop checkpoint

`core/runtime/runtime_autonomous_checkpoint.py`

Required persisted fields:

- `runtime_session_id`
- `active_cursor`
- `current_tick_index`
- `last_completed_work_id`
- `lease_id`
- `lease_expiry_tick`
- `runtime_state`
- `paused`
- `stopped`

Checkpoint validation is deterministic. Missing records deny with `checkpoint_missing`; malformed records deny with the first stable validation problem.

### Session persistence

`core/runtime/runtime_autonomous_persistence.py`

Persistence writes a JSON-safe checkpoint envelope to a caller-supplied path and reloads the same envelope. It records `runtime_state_mutated=False`, `cursor_advanced=False`, and `work_started=False`.

### Crash recovery resume gate

`core/runtime/runtime_autonomous_resume_gate.py`

Resume is allowed only from a valid, active checkpoint. Deterministic denial reasons:

- `checkpoint_missing`
- `checkpoint_invalid`
- `runtime_stopped`
- `runtime_paused`
- `lease_expired_renewal_not_authorized`

Expired leases require explicit renewal authority before resume may proceed.

### Lease renewal cycle gate

`core/runtime/runtime_autonomous_lease_renewal.py`

Renewal is allowed only when the checkpoint state is `active`, the renewal request is explicitly authorized, the renewal TTL is positive, and the emergency stop flag is false.

Deterministic denial reasons:

- `checkpoint_missing`
- `checkpoint_invalid`
- `missing_renewal_request`
- `runtime_not_active`
- `emergency_stop_active`
- `renewal_not_authorized`
- `non_positive_renewal_ttl`

## Validation

`python -m pytest tests/test_runtime_autonomous_persistence_survival_bundle.py -q`

## Final Decision

GO for Runtime Autonomous Persistence and Survival only.
