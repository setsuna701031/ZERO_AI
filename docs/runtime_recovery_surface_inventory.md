# Runtime Recovery Surface Inventory

## Package

Package 180: Runtime Recovery Surface Inventory

## Purpose

This inventory lists the Runtime surfaces that may eventually participate in Recovery integration and classifies their current authority. It is a documentation seal only and does not inspect, import, call, or modify any Runtime surface.

## Inventory classification

| Surface | Current Package 180 status | Future integration posture | Notes |
| --- | --- | --- | --- |
| `runtime_recovery_single_entry` | allowed declaration | first and only initial entry | Owns the Recovery-facing entry name |
| Scheduler | not bound | future candidate source | Must not be called by this package |
| Operator | not bound | future candidate source | Must not be called by this package |
| Dispatcher | not bound | future candidate router | Must not be called by this package |
| Supervisor | not bound | future candidate source | Must not be called by this package |
| Native Runtime | not bound | future candidate source | Must not be called by this package |
| Recovery Executor | not created | future execution owner | Out of scope until execution is explicitly enabled |

## Surface states

Package 180 recognizes these surface states:

- `not_declared`
- `declared_only`
- `dry_run_only`
- `observe_only`
- `preflight_only`
- `bound_disabled`
- `bound_guarded`
- `enabled_controlled`

For Package 180, every Runtime surface except `runtime_recovery_single_entry` remains `not_declared` or `declared_only`. No Runtime surface may become `bound_disabled`, `bound_guarded`, or `enabled_controlled` in this package.

## Inventory rules

- Inventory is static contract data.
- Inventory does not scan source files.
- Inventory does not import Runtime modules.
- Inventory does not call Runtime behavior.
- Inventory does not emit events.
- Inventory does not mutate state.
- Inventory does not enable Recovery.

## Single-entry rule

The only allowed initial Recovery entry remains:

```text
runtime_recovery_single_entry
```

Multiple direct entries are forbidden until a later package explicitly introduces and validates a fan-in model.

## Canonical event rule

Any future surface that becomes eligible for Recovery routing must project into the canonical Recovery event schema before it can proceed to preflight or binding review.

Required event fields remain:

- `contract`
- `source_surface`
- `entry_id`
- `route_id`
- `gate_state`
- `event_emitted`

## Forbidden behavior

Package 180 must not:

- execute Recovery
- enable Recovery by default
- perform recovery actions
- mutate runtime state
- emit real runtime events
- persist state
- replay state
- audit or journal events
- spawn subprocesses
- perform file IO from runtime modules
- call Scheduler
- call Operator
- call Dispatcher
- call Supervisor
- call Native Runtime
- create or call a Recovery Executor
- run broad validation

## GO / NO-GO

Final decision: GO.

Package 180 authorizes Package 181 to define a Runtime Recovery binding policy over this inventory, but it does not authorize active Runtime wiring.

## Non-mainline issues

- Package 139 documentation drift remains out of scope: older schema field names differ from the Package 140 validation shape.
- Pre-existing untracked AER runtime/docs/tests files and package sequence edits may exist in the worktree. Package 180 preserves unrelated worktree noise.
