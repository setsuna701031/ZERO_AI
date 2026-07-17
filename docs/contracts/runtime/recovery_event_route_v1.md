# Runtime Recovery Event Route Contract v1

## Purpose

Package 169 defines passive Runtime Recovery event route preparation.

Event routing produces deterministic plain dict reports only.

This contract does not execute Recovery, enable Recovery by default, perform recovery actions, mutate runtime state, persist, replay, audit, journal, call subprocess, perform file IO, emit events, or call Scheduler, Operator, Dispatcher, Runtime Supervisor, or Native Runtime behavior.

## Required Inputs

Event route preparation may consume only:

- `aer.runtime.recovery.controlled_activation_report.v1`
- `aer.runtime.recovery.kill_switch_report.v1`

The kill switch must be disabled, off, and safe.

## Single Entry Route

The only allowed route entry is:

- `runtime_recovery_single_entry`

Multiple runtime entry surfaces remain forbidden.

## Canonical Event Schema

Every event route report must include one canonical event object.

Canonical event fields:

- `contract`
- `source_surface`
- `entry_id`
- `route_id`
- `gate_state`
- `event_emitted`

Required canonical event contract:

- `aer.runtime.recovery.canonical_event.v1`

Even while routing is passive, source information must be preserved so future activation does not require a data shape change.

## Route Report Defaults

Default route reports must set:

- `route_enabled` to `false`
- `event_emitted` to `false`
- `recovery_enabled` to `false`
- `single_entry_only` to `true`
- `route_only` to `true`
- `executes_recovery` to `false`
- `side_effects_performed` to `false`

## Denied Capabilities

The event route denies:

- event emission
- Recovery execution
- Recovery enablement
- runtime mainline wiring
- multi-entry wiring
- scheduler calls
- operator calls
- dispatcher calls
- supervisor calls
- native runtime calls
- runtime mutation
- persistence writes
- replay actions
- audit emissions
- journal events
- subprocess calls
- file IO

## GO / NO-GO

Final decision: GO.

Runtime Recovery Event Route Contract v1 is complete as a passive route contract.

## Next Package

Next package: Package 170.
