# Runtime Recovery Controlled Activation Permit Contract v1

## Purpose

Package 345 defines the Recovery Controlled Activation Permit v1 contract after the disabled authorization milestone.

Contract/specification only.

Schema name: `aer.runtime.recovery.controlled_activation_permit.v1`.

This contract defines a disabled-by-default permit shape and deterministic default permit result. It separates activation permit from authorization, activation execution, gateway admission, scheduler wiring, dispatcher wiring, executor wiring, and runtime state mutation.

## Required Permit Fields

- `enabled`
- `permit_status`
- `permit_version`
- `authorization_status`
- `activation_allowed`
- `execution_allowed`
- `recovery_enabled`
- `runtime_state_mutated`
- `reason`
- `metadata`

## Default Permit Values

- `enabled: false`
- `permit_status: reserved`
- `permit_version: v1_reserved`
- `authorization_status: disabled`
- `activation_allowed: false`
- `execution_allowed: false`
- `recovery_enabled: false`
- `runtime_state_mutated: false`
- `reason: future_package`
- `metadata: {}`

## Vocabulary

Permit status vocabulary is reserved for future controlled activation packages.

Authorization source vocabulary is reserved and defaults to disabled.

Activation permission vocabulary is reserved and defaults to not allowed.

Execution permission vocabulary is reserved and defaults to not allowed.

Recovery enablement vocabulary is reserved and defaults to disabled.

Runtime mutation boundary vocabulary is reserved and defaults to not mutated.

## Compatibility Boundary

Recovery Controlled Activation Permit v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

## Forbidden Behaviors

Package 345 must not add runtime behavior, add activation behavior, approve real authorization, approve real activation, issue a real permit, execute recovery, mutate runtime state, modify scheduler wiring, modify dispatcher wiring, modify executor wiring, modify gateway behavior, connect historical recovery bridge modules, connect historical recovery executor modules, connect historical recovery adapter modules, connect historical recovery integration modules, import runtime implementation modules, start background workers, create threads, create timers, write checkpoints, restore checkpoints, perform rollback, perform retry, perform subprocess calls, invoke endpoints, register hooks, enable feature flags, modify CI, install dependencies, or modify PATH, venv, pip, bundled Python, or execution environment.

Final decision: GO for disabled permit contract only. Next package: Package 346.
