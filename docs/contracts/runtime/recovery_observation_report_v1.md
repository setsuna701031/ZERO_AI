# Runtime Recovery Observation Report Contract v1

## Purpose

Package 177 defines Runtime Recovery observation reports.

Observation reports combine Package 176 observe-only surface probe data with Package 173 dry-run route data. Reports are deterministic plain dicts only.

This contract does not execute Recovery, enable Recovery by default, perform recovery actions, mutate runtime state, persist, replay, audit, journal, call subprocess, perform file IO, emit real runtime events, or call Scheduler, Operator, Dispatcher, Runtime Supervisor, or Native Runtime behavior.

## Required Inputs

Observation reports may consume only:

- `aer.runtime.recovery.surface_probe_report.v1`
- `aer.runtime.recovery.dry_run_route_report.v1`

Both inputs must reference `runtime_recovery_single_entry`.

## Canonical Event Preservation

Observation reports must preserve the Package 169 canonical event schema without emitting it.

Required canonical event fields:

- `source_surface`
- `entry_id`
- `route_id`
- `gate_state`
- `event_emitted`

The `event_emitted` value must remain `false`.

## Report Defaults

Every observation report must keep:

- `observe_only` as `true`
- `dry_run` as `true`
- `observation_complete` as `true`
- `runtime_surface_touched` as `false`
- `surface_probe_executed` as `false`
- `event_emitted` as `false`
- `recovery_enabled` as `false`
- `single_entry_only` as `true`
- `executes_recovery` as `false`
- `side_effects_performed` as `false`

## Boundary Preservation

Packages 171 through 174 remain dry-run only.

Package 175 observation binding remains observe-only.

Package 176 surface probe data must not become a runtime probe.

Package 169 canonical event schema remains unchanged.

Recovery remains disabled by default.

## GO / NO-GO

Final decision: GO.

Runtime Recovery Observation Report Contract v1 is complete as an observe-only report contract.

## Next Package

Next package: Package 178.
