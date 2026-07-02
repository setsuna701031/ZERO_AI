# Runtime Recovery Binding Endpoint Invocation Report v1

Package 209 defines the disabled Runtime Recovery binding endpoint invocation report.

## Contract ID

`aer.runtime.recovery.binding_endpoint_invocation_report.v1`

## Purpose

The invocation report describes that an endpoint exists as disabled data and remains non-invokable. It is a dry integration surface for future Runtime wiring validation.

## Required Safety Fields

A valid invocation report must preserve:

- `endpoint_enabled: false`
- `endpoint_invokable: false`
- `endpoint_invoked: false`
- `invocation_allowed: false`
- `binding_disabled: true`
- `binding_applied: false`
- `runtime_hook_registered: false`
- `runtime_mainline_wiring_enabled: false`
- `event_emitted: false`
- `recovery_enabled: false`
- `executes_recovery: false`
- `side_effects_performed: false`
- `plain_dict_only: true`

## Boundary

The invocation report does not invoke a Runtime endpoint. It does not emit events, mutate runtime state, call scheduler/operator/supervisor/native runtime behavior, or execute Recovery.
