# Runtime Recovery Single Entry Binding Contract v1

## Purpose

Package 171 defines the Runtime Recovery single entry binding contract.

The binding contract is dry-run only. It describes how `runtime_recovery_single_entry` may be referenced by future dry-run route integration without binding Recovery to runtime execution.

This contract does not execute Recovery, enable Recovery by default, perform recovery actions, mutate runtime state, persist, replay, audit, journal, call subprocess, perform file IO, emit real runtime events, or call Scheduler, Operator, Dispatcher, Runtime Supervisor, or Native Runtime behavior.

## Single Entry Binding Rule

The only allowed binding entry is:

- `runtime_recovery_single_entry`

No other runtime entry surface may be bound, aliased, or substituted.

## Required Upstream Boundary

Single entry binding may consume only Package 169 passive event route data and Package 168 kill-switch data.

The event route must preserve the Package 169 canonical event schema:

- `source_surface`
- `entry_id`
- `route_id`
- `gate_state`
- `event_emitted`

The kill switch must remain disabled, off, and safe.

## Binding Defaults

Every binding report must keep:

- `dry_run` as `true`
- `single_entry_only` as `true`
- `binding_entry` as `runtime_recovery_single_entry`
- `bound_to_runtime` as `false`
- `binding_enabled` as `false`
- `route_enabled` as `false`
- `event_emitted` as `false`
- `recovery_enabled` as `false`
- `executes_recovery` as `false`
- `side_effects_performed` as `false`

Prepared binding data is not permission to activate Recovery.

## Preserved Boundaries

Packages 155 through 170 remain passive and preparatory.

Package 163 through Package 166 gate OFF semantics remain intact.

Package 168 kill-switch OFF semantics remain intact.

Package 169 canonical event schema remains intact.

## Denied Capabilities

The binding contract denies:

- Recovery execution
- Recovery enablement
- runtime mainline wiring
- multi-entry binding
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
- real runtime event emission
- subprocess calls
- file IO

## GO / NO-GO

Final decision: GO.

Runtime Recovery Single Entry Binding Contract v1 is complete as a dry-run binding contract.

## Next Package

Next package: Package 172.
