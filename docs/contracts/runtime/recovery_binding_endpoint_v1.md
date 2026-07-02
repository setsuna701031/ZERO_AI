# Runtime Recovery Binding Endpoint v1

Package 207 defines the disabled Runtime Recovery binding endpoint contract.

## Contract ID

`aer.runtime.recovery.binding_endpoint_report.v1`

## Endpoint

The only declared endpoint is `runtime_recovery_binding_endpoint`.

## Ownership

This package owns only the disabled endpoint data shape. It does not own Runtime hook registration, Runtime mainline wiring, Recovery execution, endpoint invocation, scheduler behavior, operator behavior, supervisor behavior, native runtime behavior, event emission, persistence, replay, audit, journal, subprocess, or file IO.

## Required Safety Fields

A valid endpoint report must preserve:

- `endpoint_declared: true`
- `endpoint_enabled: false`
- `endpoint_invokable: false`
- `binding_disabled: true`
- `binding_applied: false`
- `runtime_hook_registered: false`
- `runtime_mainline_wiring_enabled: false`
- `event_emitted: false`
- `recovery_enabled: false`
- `admission_granted: false`
- `executes_recovery: false`
- `side_effects_performed: false`
- `plain_dict_only: true`

## Statuses

Allowed statuses are `prepared`, `blocked`, and `denied`.

`prepared` means the endpoint is described as disabled data only. It does not mean the endpoint can be invoked.

`blocked` means the upstream admission report or requested endpoint is incompatible.

`denied` means the caller requested activation or explicitly requested denied status.

## Boundary

The endpoint helper must return deterministic plain dictionaries only. It must not register a hook, apply a binding, mutate runtime state, emit events, execute Recovery, or call Runtime surfaces.
