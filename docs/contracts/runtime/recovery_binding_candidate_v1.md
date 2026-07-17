# Recovery Binding Candidate v1

Package 191 defines the passive Runtime Recovery binding candidate contract.

## Scope

The candidate contract describes a future binding candidate for the single Runtime Recovery entry. It does not apply a binding, register a hook, enable Recovery, emit an event, mutate runtime state, or call runtime behavior.

## Public Contract

- contract: `aer.runtime.recovery.binding_candidate.v1`
- single entry: `runtime_recovery_single_entry`
- statuses: `prepared`, `blocked`, `denied`
- binding_application_allowed: `False`
- binding_registered: `False`
- runtime_bound: `False`
- runtime_mainline_wiring_enabled: `False`
- event_emitted: `False`
- recovery_enabled: `False`
- approval_required: `True`
- executes_recovery: `False`
- side_effects_performed: `False`
- plain_dict_only: `True`

## Boundary Rules

The package must not execute Recovery, enable Recovery, register hooks, apply bindings, call Scheduler, call Operator, call Dispatcher, call Supervisor, call Native Runtime, persist, replay, audit, journal, spawn subprocesses, or perform file IO.

## GO / NO-GO

GO only when the candidate is prepared from a compatible passive binding plan and remains unbound and approval-gated.
