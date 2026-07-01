# Recovery Binding Admission v1

## Package

Package 203: Runtime Recovery Binding Admission Contract

## Contract IDs

- `aer.runtime.recovery.binding_admission_evaluation.v1`
- `aer.runtime.recovery.binding_admission_report.v1`

## Purpose

Recovery Binding Admission v1 is the final disabled Runtime-side gate before any
future controlled Runtime wiring package may be considered. It evaluates the
Package 199 disabled binding skeleton and Package 201 runtime binding points as
contract data only.

Admission does not mean approval is granted. In this package family admission is
explicitly not granted; it is only represented as a non-executing report shape.

## Required Entry

Only one entry is admissible:

- `runtime_recovery_single_entry`

All multi-surface admission, scheduler admission, operator admission, supervisor
admission, native runtime admission, dispatcher admission, and direct runtime
mainline admission are forbidden.

## Required Safe Defaults

Every admission evaluation and report must keep:

- `admission_allowed: false`
- `admission_granted: false` when present
- `binding_admitted: false`
- `runtime_accepts_binding: false`
- `runtime_hook_registered: false`
- `runtime_binding_applied: false`
- `binding_enabled: false`
- `recovery_enabled: false`
- `event_emitted: false`
- `executes_recovery: false`
- `side_effects_performed: false`
- `plain_dict_only: true`

## Canonical Event Preservation

Admission payloads may carry the Package 169 canonical event reference forward,
but they must not emit it. The canonical event must remain inert and must keep
`event_emitted: false`.

## Forbidden Behavior

Recovery Binding Admission v1 must not:

- execute Recovery
- enable Recovery
- grant admission
- accept binding into Runtime
- register runtime hooks
- apply runtime binding
- wire Runtime mainline
- activate routes
- emit events
- mutate runtime state
- call scheduler, operator, dispatcher, supervisor, or native runtime behavior
- persist, replay, audit, journal, subprocess, or perform file IO

## Future Ownership

Future wiring packages may consume the admission report, but they must define a
new controlled-wiring contract before any Runtime hook is registered or binding
is applied.
