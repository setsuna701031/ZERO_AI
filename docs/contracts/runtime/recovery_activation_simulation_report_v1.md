# Runtime Recovery Activation Simulation Report v1

## Package

Package 217: Runtime Recovery Activation Simulation Report

## Contract

`aer.runtime.recovery.activation_simulation_report.v1`

## Purpose

This report records the result of a disabled activation simulation without committing activation, opening the gate, invoking the endpoint, or changing Runtime behavior.

## Owned Surface

- simulation report contract id
- simulation reference
- simulation state
- activation commit denial
- stable disabled flags
- denied capability list
- deterministic plain-dict report shape

## Required Properties

A valid simulation report must preserve:

- `simulation_state: not_applied`
- `simulation_committed: false`
- `activation_commit_allowed: false`
- `activation_state: disabled`
- `gate_state: closed`
- `gate_open: false`
- `activation_granted: false`
- `activation_allowed: false`
- `recovery_enabled: false`
- `binding_applied: false`
- `runtime_hook_registered: false`
- `event_emitted: false`
- `executes_recovery: false`
- `side_effects_performed: false`
- `plain_dict_only: true`

## Must Not

This report must not:

- approve or commit activation
- become runtime activation authority
- register hooks
- apply binding
- execute Recovery
- emit events
- mutate runtime state
- call runtime behavior
