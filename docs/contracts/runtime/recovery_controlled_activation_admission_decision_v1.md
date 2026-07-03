# Runtime Recovery Controlled Activation Admission Decision Contract v1

## Purpose

Package 401 defines the Recovery Controlled Activation Admission Decision v1 contract.

Contract/specification only.

Schema name: `aer.runtime.recovery.controlled_activation_admission_decision.v1`.

This contract defines a disabled-by-default admission decision record shape and deterministic default result. It exposes decision record, status, and eligibility information only. It separates admission decision records from authorization effect, activation, recovery execution, runtime wiring, gateway mutation, scheduler wiring, dispatcher wiring, executor wiring, and runtime state mutation.

## Required Admission Decision Fields

- `enabled`
- `admission_decision_status`
- `admission_decision_version`
- `admission_decision_eligible`
- `admission_decision_recorded`
- `admission_decision_effective`
- `admission_approved`
- `authorization_effective`
- `activation_allowed`
- `execution_permission_granted`
- `recovery_enabled`
- `runtime_state_mutated`
- `reason`
- `metadata`

## Default Admission Decision Values

- `enabled: false`
- `admission_decision_status: reserved`
- `admission_decision_version: v1_reserved`
- `admission_decision_eligible: false`
- `admission_decision_recorded: false`
- `admission_decision_effective: false`
- `admission_approved: false`
- `authorization_effective: false`
- `activation_allowed: false`
- `execution_permission_granted: false`
- `recovery_enabled: false`
- `runtime_state_mutated: false`
- `reason: future_package`
- `metadata: {}`

## Vocabulary

Admission decision status vocabulary is reserved for future admission decision packages.

Decision eligibility vocabulary is reserved and defaults to not eligible.

Decision record vocabulary is reserved and defaults to not recorded and not effective.

Admission approval vocabulary is reserved and defaults to not approved.

Authorization effect vocabulary is reserved and defaults to not effective.

Activation vocabulary is reserved and defaults to not allowed.

Execution permission vocabulary is reserved and defaults to not granted.

Recovery enablement vocabulary is reserved and defaults to disabled.

Runtime mutation boundary vocabulary is reserved and defaults to not mutated.

## Compatibility Boundary

Recovery Controlled Activation Admission Decision v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

## Non-Authorization Boundary

Admission decision records are not authorization.

Admission decision records cannot make authorization effective.

Admission decision records cannot authorize activation.

## Non-Activation Boundary

Admission decision records cannot activate recovery.

Admission decision records cannot start activation.

Admission decision records cannot enable recovery.

## Non-Execution Boundary

Admission decision records cannot grant execution permission.

Admission decision records cannot execute recovery.

Admission decision records cannot dispatch recovery.

## Runtime Mutation Boundary

Admission decision records are not runtime wiring.

Admission decision records are not scheduler wiring.

Admission decision records are not dispatcher wiring.

Admission decision records are not executor wiring.

Admission decision records are not gateway mutation.

Admission decision records cannot mutate runtime state.

## Forbidden Behaviors

Packages 401-408 must not add runtime behavior, make real admission decisions, approve admission, make authorization effective, activate recovery, enable recovery, execute recovery, mutate runtime state, modify scheduler, modify dispatcher, modify executor, modify gateway, connect runtime wiring, call historical recovery bridge modules, call historical recovery executor modules, call historical recovery adapter modules, call historical recovery integration modules, write checkpoints, restore checkpoints, perform rollback, perform retry, perform subprocess calls, start workers, create threads, create timers, register hooks, modify CI, install dependencies, or modify PATH, venv, pip, bundled Python, or execution environment.

Final decision: GO for disabled admission decision contract only. Next package: Package 402.
