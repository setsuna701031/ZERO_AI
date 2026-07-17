# Recovery Binding Approval Report v1

Package 193 defines the passive Runtime Recovery binding approval report contract.

## Scope

The approval report is the future handoff surface for an approved binding chain, but this package never grants approval and never applies a binding. `approval_granted` is always `False`.

## Public Contract

- contract: `aer.runtime.recovery.binding_approval_report.v1`
- approval_report_prepared: `True` only for compatible validator reports
- approval_required: `True`
- approval_granted: `False`
- binding_application_allowed: `False`
- binding_registered: `False`
- runtime_bound: `False`
- runtime_mainline_wiring_enabled: `False`
- event_emitted: `False`
- recovery_enabled: `False`
- executes_recovery: `False`
- side_effects_performed: `False`
- plain_dict_only: `True`

## Boundary Rules

The approval report must not grant binding authority, apply binding, register runtime hooks, execute Recovery, emit events, mutate runtime state, persist, replay, audit, journal, spawn subprocesses, perform file IO, or call runtime behavior.
