# Recovery Binding Plan v1

## Package 189

Package 189 defines a passive Recovery binding plan report. The plan composes the passive registry and preflight eligibility into a deterministic dict, but it does not apply runtime binding.

## Contract ID

`aer.runtime.recovery.binding_plan.v1`

## Public Helper

`prepare_recovery_binding_plan_report(...)`

## Required Output Semantics

- `binding_plan_only` is `True`.
- `binding_entry` is `runtime_recovery_single_entry` for valid prepared reports.
- `binding_planned` may be `True` only for prepared reports.
- `binding_applied` is always `False`.
- `runtime_binding_registered` is `False`.
- `runtime_binding_active` is `False`.
- `runtime_mainline_wiring_allowed` is `False`.
- `event_emitted` is `False`.
- `recovery_enabled` is `False`.
- Canonical event data is preserved from preflight.

## Forbidden Behavior

The helper must not bind, activate, execute Recovery, emit events, mutate runtime, persist, replay, audit, journal, spawn subprocesses, perform file IO, or call runtime surface behavior.
