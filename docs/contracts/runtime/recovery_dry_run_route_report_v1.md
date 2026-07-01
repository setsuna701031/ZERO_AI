# Runtime Recovery Dry-Run Route Report Contract v1

## Purpose

Package 173 defines Runtime Recovery dry-run route integration reports.

Dry-run route reports combine Package 169 passive event route data with Package 172 dry-run binding data. Reports are deterministic plain dicts only.

This contract does not execute Recovery, enable Recovery by default, perform recovery actions, mutate runtime state, persist, replay, audit, journal, call subprocess, perform file IO, emit real runtime events, or call Scheduler, Operator, Dispatcher, Runtime Supervisor, or Native Runtime behavior.

## Required Inputs

Dry-run route reports may consume only:

- `aer.runtime.recovery.event_route_report.v1`
- `aer.runtime.recovery.dry_run_binding_report.v1`

Both inputs must reference `runtime_recovery_single_entry`.

## Canonical Event Preservation

Dry-run route reports must preserve the Package 169 canonical event schema without emitting it.

Required canonical event fields:

- `source_surface`
- `entry_id`
- `route_id`
- `gate_state`
- `event_emitted`

The `event_emitted` value must remain `false`.

## Report Defaults

Every dry-run route report must keep:

- `dry_run` as `true`
- `route_integrated` as `false`
- `binding_enabled` as `false`
- `route_enabled` as `false`
- `event_emitted` as `false`
- `recovery_enabled` as `false`
- `single_entry_only` as `true`
- `executes_recovery` as `false`
- `side_effects_performed` as `false`

## Boundary Preservation

Packages 155 through 172 remain passive and preparatory.

Package 169 canonical event schema remains unchanged.

Package 172 dry-run binding data is not runtime binding permission.

Recovery remains disabled by default.

## GO / NO-GO

Final decision: GO.

Runtime Recovery Dry-Run Route Report Contract v1 is complete as a dry-run route integration contract.

## Next Package

Next package: Package 174.
