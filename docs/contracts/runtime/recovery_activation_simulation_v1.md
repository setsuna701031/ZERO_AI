# Runtime Recovery Activation Simulation v1

## Package

Package 215: Runtime Recovery Activation Simulation Contract

## Contract

`aer.runtime.recovery.activation_simulation.v1`

## Purpose

This contract defines the disabled Runtime Recovery activation simulation surface after the Activation Gate layer. The simulation proves that the activation chain can be evaluated as data while Recovery remains disabled.

## Owned Surface

- activation simulation contract id
- accepted activation gate report reference
- disabled activation state
- closed gate state
- non-applied simulation result
- denied runtime capabilities
- deterministic plain-dict output

## Required Properties

A valid simulation payload must preserve:

- `activation_state: disabled`
- `gate_state: closed`
- `gate_open: false`
- `gate_enabled: false`
- `activation_granted: false`
- `activation_allowed: false`
- `recovery_enabled: false`
- `binding_disabled: true`
- `binding_applied: false`
- `runtime_hook_registered: false`
- `runtime_mainline_wiring_enabled: false`
- `endpoint_invoked: false`
- `event_emitted: false`
- `simulation_applied: false`
- `simulation_result: not_applied`
- `executes_recovery: false`
- `side_effects_performed: false`
- `plain_dict_only: true`

## Must Not

This package must not:

- execute Recovery
- enable Recovery
- open an activation gate
- grant activation
- commit activation simulation
- register runtime hooks
- apply runtime binding
- invoke runtime endpoints
- emit events
- mutate runtime state
- call scheduler, operator, dispatcher, supervisor, or native runtime behavior
- persist, replay, audit, journal, subprocess, or perform file IO

## Future Packages

Future packages may define runtime wiring validation only after simulation remains disabled and sealed.
