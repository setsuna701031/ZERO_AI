# Runtime Recovery Controlled Activation Commit Contract v1

## Purpose

Package 361 defines the Recovery Controlled Activation Commit v1 contract.

Contract/specification only.

Schema name: `aer.runtime.recovery.controlled_activation_commit.v1`.

This contract defines a disabled-by-default commit shape and deterministic default result. It separates activation commit from activation execution, gateway admission, scheduler wiring, dispatcher wiring, executor wiring, and runtime state mutation.

## Required Commit Fields

- `enabled`
- `commit_status`
- `commit_version`
- `grant_consumed`
- `permit_consumed`
- `authorization_confirmed`
- `activation_committed`
- `activation_allowed`
- `execution_allowed`
- `recovery_enabled`
- `runtime_state_mutated`
- `reason`
- `metadata`

## Default Commit Values

- `enabled: false`
- `commit_status: reserved`
- `commit_version: v1_reserved`
- `grant_consumed: false`
- `permit_consumed: false`
- `authorization_confirmed: false`
- `activation_committed: false`
- `activation_allowed: false`
- `execution_allowed: false`
- `recovery_enabled: false`
- `runtime_state_mutated: false`
- `reason: future_package`
- `metadata: {}`

## Vocabulary

Commit status vocabulary is reserved for future controlled activation packages.

Grant consumption vocabulary is reserved and defaults to not consumed.

Permit consumption vocabulary is reserved and defaults to not consumed.

Authorization boundary vocabulary is reserved and defaults to not confirmed.

Activation permission vocabulary is reserved and defaults to not allowed.

Execution permission vocabulary is reserved and defaults to not allowed.

Recovery enablement vocabulary is reserved and defaults to disabled.

Runtime mutation boundary vocabulary is reserved and defaults to not mutated.

## Compatibility Boundary

Recovery Controlled Activation Commit v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

## Separation Boundary

Activation commit is not activation execution.

Activation commit is not gateway admission.

Activation commit is not scheduler wiring.

Activation commit is not dispatcher wiring.

Activation commit is not executor wiring.

Activation commit is not runtime state mutation.

## Forbidden Behaviors

Package 361 must not add runtime behavior, add activation behavior, approve real commit, consume grants, consume permits, confirm real authorization, approve real activation, execute recovery, mutate runtime state, modify scheduler wiring, modify dispatcher wiring, modify executor wiring, modify gateway behavior, connect historical recovery bridge modules, connect historical recovery executor modules, connect historical recovery adapter modules, connect historical recovery integration modules, import runtime implementation modules, start background workers, create threads, create timers, write checkpoints, restore checkpoints, perform rollback, perform retry, perform subprocess calls, invoke endpoints, register hooks, enable feature flags, modify CI, install dependencies, or modify PATH, venv, pip, bundled Python, or execution environment.

Final decision: GO for disabled contract only. Next package: Package 362.
