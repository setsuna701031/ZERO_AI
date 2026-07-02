# Recovery Activation Gate v1

## Package

Package 211: Runtime Recovery Activation Gate Contract.

## Purpose

`aer.runtime.recovery.activation_gate.v1` defines the disabled activation gate between the disabled binding endpoint invocation layer and any future Runtime Recovery activation layer.

The gate is declarative and closed by default. It may prepare a plain report that says whether the gate shape is valid, but it must not open the gate, grant activation, enable Recovery, register hooks, apply bindings, emit events, mutate runtime state, or execute Recovery.

## Public Contract

Schema id: `aer.runtime.recovery.activation_gate.v1`

Allowed statuses:

- `prepared`
- `blocked`
- `denied`

Required disabled fields:

- `gate_declared: True`
- `gate_enabled: False`
- `gate_open: False`
- `activation_allowed: False`
- `activation_gate_enabled: False`
- `activation_gate_opened: False`
- `kill_switch_required: True`
- `admission_required: True`
- `endpoint_invocation_required: True`
- `endpoint_invoked: False`
- `binding_disabled: True`
- `binding_applied: False`
- `runtime_hook_registered: False`
- `event_emitted: False`
- `recovery_enabled: False`
- `executes_recovery: False`
- `side_effects_performed: False`
- `plain_dict_only: True`

## Upstream Boundary

The only allowed upstream input is a disabled binding endpoint invocation report with schema:

`aer.runtime.recovery.binding_endpoint_invocation_report.v1`

The upstream report must prove that the endpoint was declared but not enabled, not invokable, not invoked, and did not emit an event.

## Forbidden Behavior

Package 211 must not:

- execute Recovery
- enable Recovery
- open the activation gate
- grant activation
- register runtime hooks
- apply runtime bindings
- invoke endpoints
- emit runtime events
- mutate runtime state
- call scheduler, operator, dispatcher, supervisor, or native runtime
- persist, replay, audit, journal, subprocess, or perform file IO

## Future Packages

Future packages may introduce activation simulation or controlled runtime wiring only after this gate remains closed by default and after a dedicated readiness review authorizes the next step.

## GO / NO-GO

Final decision: GO.

Next package: Package 212.

## Non-mainline Issues Found

- None for Package 211.
