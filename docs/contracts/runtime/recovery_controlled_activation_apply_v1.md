# Runtime Recovery Controlled Activation Apply Contract v1

## Purpose

Package 369 defines the Recovery Controlled Activation Apply v1 contract.

Contract/specification only.

Schema name: `aer.runtime.recovery.controlled_activation_apply.v1`.

This contract defines a disabled-by-default apply shape and deterministic default result. It separates activation apply from activation execution, gateway admission, scheduler wiring, dispatcher wiring, executor wiring, and runtime state mutation.

## Required Apply Fields

- `enabled`
- `apply_status`
- `apply_version`
- `commit_consumed`
- `grant_consumed`
- `permit_consumed`
- `authorization_confirmed`
- `activation_applied`
- `activation_allowed`
- `execution_allowed`
- `recovery_enabled`
- `runtime_state_mutated`
- `reason`
- `metadata`

## Default Apply Values

- `enabled: false`
- `apply_status: reserved`
- `apply_version: v1_reserved`
- `commit_consumed: false`
- `grant_consumed: false`
- `permit_consumed: false`
- `authorization_confirmed: false`
- `activation_applied: false`
- `activation_allowed: false`
- `execution_allowed: false`
- `recovery_enabled: false`
- `runtime_state_mutated: false`
- `reason: future_package`
- `metadata: {}`

## Vocabulary

Apply status vocabulary is reserved for future controlled activation packages.

Commit consumption vocabulary is reserved and defaults to not consumed.

Grant consumption vocabulary is reserved and defaults to not consumed.

Permit consumption vocabulary is reserved and defaults to not consumed.

Authorization boundary vocabulary is reserved and defaults to not confirmed.

Activation permission vocabulary is reserved and defaults to not allowed.

Execution permission vocabulary is reserved and defaults to not allowed.

Recovery enablement vocabulary is reserved and defaults to disabled.

Runtime mutation boundary vocabulary is reserved and defaults to not mutated.

## Compatibility Boundary

Recovery Controlled Activation Apply v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

## Separation Boundary

Activation apply is not activation execution.

Activation apply is not gateway admission.

Activation apply is not scheduler wiring.

Activation apply is not dispatcher wiring.

Activation apply is not executor wiring.

Activation apply is not runtime state mutation.

## Forbidden Behaviors

Package 369 must not add runtime behavior, add activation behavior, approve real apply, consume commit, consume grant, consume permit, confirm real authorization, approve real activation, execute recovery, mutate runtime state, modify scheduler wiring, modify dispatcher wiring, modify executor wiring, modify gateway behavior, connect historical recovery bridge modules, connect historical recovery executor modules, connect historical recovery adapter modules, connect historical recovery integration modules, import runtime implementation modules, start background workers, create threads, create timers, write checkpoints, restore checkpoints, perform rollback, perform retry, perform subprocess calls, invoke endpoints, register hooks, enable feature flags, modify CI, install dependencies, or modify PATH, venv, pip, bundled Python, or execution environment.

Final decision: GO for disabled contract only. Next package: Package 370.
