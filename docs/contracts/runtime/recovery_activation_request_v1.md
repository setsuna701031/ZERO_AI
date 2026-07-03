# Runtime Recovery Activation Request Contract v1

## Purpose

Package 281 defines Runtime Recovery Activation Request Contract v1.

Contract/documentation only.

Default Runtime Recovery activation remains disabled. This contract does not execute recovery, mutate runtime state, write checkpoints, restore checkpoints, execute rollback or retry, spawn subprocesses, invoke endpoints, register hooks, add persistence, or activate gateway, supervisor, operator, scheduler, planner, or native runtime behavior.

## Public Contract Names

Package 281 defines these public contract names:

- RecoveryActivationRequest
- RecoveryActivationResult
- RecoveryActivationFailure
- RecoveryActivationPolicy
- RecoveryActivationOwnership
- RecoveryActivationLifecycle

No public runtime API is introduced by this contract document.

## Activation Request Shape

RecoveryActivationRequest is reserved plain data only.

Required fields:

- contract_name: "RecoveryActivationRequest"
- contract_version: "v1"
- activation_request_id
- requested_by
- activation_reason
- activation_mode
- metadata

Package 281 does not construct or consume RecoveryActivationRequest at runtime.

## Activation Result Shape

RecoveryActivationResult is reserved plain data only.

Required fields:

- contract_name: "RecoveryActivationResult"
- contract_version: "v1"
- activation_result_id
- activation_request_id
- activation_allowed
- execution_allowed
- recovery_enabled
- runtime_state_mutated
- failure
- metadata

Package 281 does not produce RecoveryActivationResult at runtime.

## Ownership Boundaries

RecoveryActivationOwnership owns future activation request and result vocabulary only.

RecoveryActivationOwnership does not own runtime execution, runtime state mutation, checkpoint write or restore, rollback execution, retry execution, gateway activation, supervisor control, operator control, scheduler routing, planner routing, native runtime activation, persistence, subprocess, endpoint invocation, or hook registration.

## Lifecycle

RecoveryActivationLifecycle reserves these future lifecycle values:

- reserved
- requested
- denied
- blocked
- allowed_future_only
- activated_future_only
- failed_future_only

Package 281 does not transition lifecycle state.

## Failure Taxonomy

RecoveryActivationFailure reserves these failure codes:

- recovery_activation_not_implemented
- recovery_activation_disabled
- activation_request_invalid
- activation_policy_reserved
- activation_gate_disabled
- admission_bridge_disabled
- execution_forbidden
- runtime_state_mutation_forbidden
- checkpoint_write_forbidden
- checkpoint_restore_forbidden
- rollback_retry_forbidden
- gateway_activation_forbidden
- supervisor_control_forbidden
- persistence_forbidden
- subprocess_forbidden
- endpoint_invocation_forbidden
- hook_registration_forbidden

## Compatibility Policy

Runtime Recovery Activation Request Contract v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

## Forbidden Runtime Behaviors

Package 281 must not create runtime modules.

Package 281 must not execute recovery.

Package 281 must not mutate runtime state.

Package 281 must not write or restore checkpoints.

Package 281 must not execute rollback or retry.

Package 281 must not spawn subprocesses.

Package 281 must not invoke endpoints.

Package 281 must not register hooks.

Package 281 must not add persistence.

Final decision: GO. Next package: Package 282.
