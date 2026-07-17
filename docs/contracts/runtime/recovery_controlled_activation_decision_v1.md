# Runtime Recovery Controlled Activation Decision Contract v1

## Purpose

Package 329 defines the Recovery Controlled Activation Decision v1 contract.

Contract/specification only.

Schema name: `aer.runtime.recovery.controlled_activation_decision.v1`.

This contract defines a disabled-by-default decision shape and a deterministic default result for future controlled activation packages. It separates activation decision from activation execution, gateway admission, scheduler wiring, dispatcher wiring, executor wiring, and runtime state mutation.

## Public Contract Names

Package 329 defines these public contract names:

- RecoveryControlledActivationDecisionRequest
- RecoveryControlledActivationDecisionResult
- RecoveryControlledActivationDecisionFailure
- RecoveryControlledActivationDecisionPolicy
- RecoveryControlledActivationDecisionOwnership
- RecoveryControlledActivationDecisionLifecycle

No public runtime API is introduced by this contract document.

## Required Decision Fields

- `enabled`
- `decision_status`
- `decision_version`
- `activation_allowed`
- `execution_allowed`
- `recovery_enabled`
- `runtime_state_mutated`
- `reason`
- `metadata`

## Default Decision Values

- `enabled: false`
- `decision_status: reserved`
- `decision_version: v1_reserved`
- `activation_allowed: false`
- `execution_allowed: false`
- `recovery_enabled: false`
- `runtime_state_mutated: false`
- `reason: future_package`
- `metadata: {}`

## Vocabulary

Decision status vocabulary is reserved for future controlled activation packages.

Activation permission vocabulary is reserved and defaults to not allowed.

Execution permission vocabulary is reserved and defaults to not allowed.

Recovery enablement vocabulary is reserved and defaults to disabled.

Runtime mutation boundary vocabulary is reserved and defaults to not mutated.

## Compatibility Boundary

Recovery Controlled Activation Decision v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

## Forbidden Behaviors

Package 329 must not add runtime behavior, add activation behavior, approve real activation, execute recovery, mutate runtime state, modify scheduler wiring, modify dispatcher wiring, modify executor wiring, modify gateway behavior, connect historical recovery bridge modules, connect historical recovery executor modules, connect historical recovery adapter modules, connect historical recovery integration modules, import runtime implementation modules, start background workers, create threads, create timers, write checkpoints, restore checkpoints, perform rollback, perform retry, perform subprocess calls, invoke endpoints, register hooks, enable feature flags, modify CI, install dependencies, or modify PATH, venv, pip, bundled Python, or execution environment.

Final decision: GO for disabled contract only. Next package: Package 330.
