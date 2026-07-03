# Runtime Recovery Controlled Activation Contract v1

## Purpose

Package 321 defines Runtime Recovery Controlled Activation Contract v1.

Contract/documentation only.

Default Runtime Recovery controlled activation remains disabled. This contract does not execute recovery, mutate runtime state, enable feature flags, wire schedulers, wire dispatchers, wire executors, mutate gateway behavior, start background workers, create threads or timers, write checkpoints, restore checkpoints, execute rollback or retry, spawn subprocesses, invoke endpoints, register hooks, add persistence, or connect historical recovery bridge, executor, adapter, or integration modules.

## Public Contract Names

Package 321 defines these public contract names:

- RecoveryControlledActivationRequest
- RecoveryControlledActivationResult
- RecoveryControlledActivationFailure
- RecoveryControlledActivationPolicy
- RecoveryControlledActivationOwnership
- RecoveryControlledActivationLifecycle

No public runtime API is introduced by this contract document.

## Controlled Activation Request Shape

RecoveryControlledActivationRequest is reserved plain data only.

Required fields:

- contract_name: "RecoveryControlledActivationRequest"
- contract_version: "v1"
- controlled_activation_request_id
- requested_by
- activation_reason
- metadata

Package 321 does not construct or consume RecoveryControlledActivationRequest at runtime.

## Controlled Activation Result Shape

RecoveryControlledActivationResult is reserved plain data only.

Required fields:

- contract_name: "RecoveryControlledActivationResult"
- contract_version: "v1"
- controlled_activation_result_id
- controlled_activation_request_id
- enabled
- activation_allowed
- execution_allowed
- recovery_enabled
- runtime_state_mutated
- reason
- failure
- metadata

Package 321 does not produce RecoveryControlledActivationResult at runtime.

## Ownership Boundaries

RecoveryControlledActivationOwnership owns future controlled activation vocabulary only.

RecoveryControlledActivationOwnership does not own recovery execution, scheduler wiring, dispatcher wiring, executor wiring, gateway behavior mutation, background workers, thread or timer creation, runtime state mutation, feature flag enabling, checkpoint write or restore, rollback execution, retry execution, persistence, subprocess, endpoint invocation, hook registration, or historical recovery bridge, executor, adapter, or integration modules.

## Lifecycle

RecoveryControlledActivationLifecycle reserves these future lifecycle values:

- reserved
- requested
- denied
- blocked
- allowed_future_only
- activated_future_only
- failed_future_only

Package 321 does not transition lifecycle state.

## Failure Taxonomy

RecoveryControlledActivationFailure reserves these failure codes:

- recovery_controlled_activation_not_implemented
- recovery_controlled_activation_disabled
- controlled_activation_request_invalid
- activation_forbidden
- execution_forbidden
- runtime_state_mutation_forbidden
- feature_flag_enablement_forbidden
- scheduler_wiring_forbidden
- dispatcher_wiring_forbidden
- executor_wiring_forbidden
- gateway_mutation_forbidden
- background_worker_forbidden
- thread_timer_forbidden
- persistence_forbidden
- subprocess_forbidden
- endpoint_invocation_forbidden
- hook_registration_forbidden

## Compatibility Policy

Runtime Recovery Controlled Activation Contract v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

Final decision: GO. Next package: Package 322.
