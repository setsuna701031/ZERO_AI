# Runtime Recovery Controlled Activation Admission Preparation Contract v1

## Purpose

Package 385 defines the Recovery Controlled Activation Admission Preparation v1 contract.

Contract/specification only.

Schema name: `aer.runtime.recovery.controlled_activation_admission_preparation.v1`.

This contract defines a disabled-by-default admission preparation shape and deterministic default result. It exposes readiness, status, and eligibility information only. It separates admission preparation from admission execution, recovery execution, runtime wiring, gateway admission, scheduler wiring, dispatcher wiring, executor wiring, authorization, activation, and runtime state mutation.

## Required Admission Preparation Fields

- `enabled`
- `admission_preparation_status`
- `admission_preparation_version`
- `admission_preparation_eligible`
- `admission_preparation_ready`
- `admission_prepared`
- `admission_allowed`
- `authorization_granted`
- `activation_allowed`
- `execution_allowed`
- `recovery_enabled`
- `runtime_state_mutated`
- `reason`
- `metadata`

## Default Admission Preparation Values

- `enabled: false`
- `admission_preparation_status: reserved`
- `admission_preparation_version: v1_reserved`
- `admission_preparation_eligible: false`
- `admission_preparation_ready: false`
- `admission_prepared: false`
- `admission_allowed: false`
- `authorization_granted: false`
- `activation_allowed: false`
- `execution_allowed: false`
- `recovery_enabled: false`
- `runtime_state_mutated: false`
- `reason: future_package`
- `metadata: {}`

## Vocabulary

Admission preparation status vocabulary is reserved for future admission packages.

Eligibility vocabulary is reserved and defaults to not eligible.

Readiness vocabulary is reserved and defaults to not ready.

Admission boundary vocabulary is reserved and defaults to not prepared and not allowed.

Authorization boundary vocabulary is reserved and defaults to not granted.

Activation permission vocabulary is reserved and defaults to not allowed.

Execution permission vocabulary is reserved and defaults to not allowed.

Recovery enablement vocabulary is reserved and defaults to disabled.

Runtime mutation boundary vocabulary is reserved and defaults to not mutated.

## Compatibility Boundary

Recovery Controlled Activation Admission Preparation v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

## Non-Authorization Boundary

Admission preparation is not authorization.

Admission preparation cannot grant authorization.

Admission preparation cannot confirm authorization.

## Non-Execution Boundary

Admission preparation is not admission execution.

Admission preparation is not activation execution.

Admission preparation is not recovery execution.

Admission preparation cannot allow execution.

## Runtime Mutation Boundary

Admission preparation is not runtime wiring.

Admission preparation is not scheduler wiring.

Admission preparation is not dispatcher wiring.

Admission preparation is not executor wiring.

Admission preparation is not gateway admission.

Admission preparation cannot mutate runtime state.

## Forbidden Behaviors

Packages 385-392 must not add runtime behavior, prepare real admission, approve admission, authorize activation, enable recovery, execute recovery, mutate runtime state, modify scheduler, modify dispatcher, modify executor, modify gateway, connect runtime wiring, call historical recovery bridge modules, call historical recovery executor modules, call historical recovery adapter modules, call historical recovery integration modules, write checkpoints, restore checkpoints, perform rollback, perform retry, perform subprocess calls, start workers, create threads, create timers, register hooks, modify CI, install dependencies, or modify PATH, venv, pip, bundled Python, or execution environment.

Final decision: GO for disabled admission preparation contract only. Next package: Package 386.
