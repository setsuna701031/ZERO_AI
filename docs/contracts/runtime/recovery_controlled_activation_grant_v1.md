# Runtime Recovery Controlled Activation Grant Contract v1

## Purpose

Package 353 defines the Recovery Controlled Activation Grant v1 contract.

Contract/specification only.

Schema name: `aer.runtime.recovery.controlled_activation_grant.v1`.

This contract defines a disabled-by-default grant shape and deterministic default result. It separates activation grant from activation execution, gateway admission, scheduler wiring, dispatcher wiring, executor wiring, and runtime state mutation.

## Required Grant Fields

- `enabled`
- `grant_status`
- `grant_version`
- `permit_granted`
- `activation_granted`
- `activation_allowed`
- `execution_allowed`
- `recovery_enabled`
- `runtime_state_mutated`
- `reason`
- `metadata`

## Default Grant Values

- `enabled: false`
- `grant_status: reserved`
- `grant_version: v1_reserved`
- `permit_granted: false`
- `activation_granted: false`
- `activation_allowed: false`
- `execution_allowed: false`
- `recovery_enabled: false`
- `runtime_state_mutated: false`
- `reason: future_package`
- `metadata: {}`

## Vocabulary

Grant status vocabulary is reserved for future controlled activation packages.

Permit consumption vocabulary is reserved and defaults to not granted.

Authorization boundary vocabulary remains disabled by default.

Activation permission vocabulary is reserved and defaults to not allowed.

Execution permission vocabulary is reserved and defaults to not allowed.

Recovery enablement vocabulary is reserved and defaults to disabled.

Runtime mutation boundary vocabulary is reserved and defaults to not mutated.

## Compatibility Boundary

Recovery Controlled Activation Grant v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

## Forbidden Behaviors

Package 353 must not add runtime behavior, add activation behavior, approve real grant issuance, approve real permit consumption, approve real authorization, approve real activation, execute recovery, mutate runtime state, modify scheduler wiring, modify dispatcher wiring, modify executor wiring, modify gateway behavior, connect historical recovery bridge modules, connect historical recovery executor modules, connect historical recovery adapter modules, connect historical recovery integration modules, import runtime implementation modules, start background workers, create threads, create timers, write checkpoints, restore checkpoints, perform rollback, perform retry, perform subprocess calls, invoke endpoints, register hooks, enable feature flags, modify CI, install dependencies, or modify PATH, venv, pip, bundled Python, or execution environment.

Final decision: GO for disabled contract only. Next package: Package 354.
