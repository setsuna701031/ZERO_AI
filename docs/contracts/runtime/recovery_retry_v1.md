# Runtime Recovery Retry Contract v1

## Purpose

Package 263 defines Runtime Recovery Retry Contract v1.

Contract/documentation only.

This package does not implement retry behavior, does not create runtime modules, does not modify gateway code, does not modify executor code, does not implement state transition, checkpoint, or rollback behavior, does not wire recovery runtime modules, and does not introduce public runtime APIs.

## Public Contract Names Only

Package 263 defines these public contract names only:

- RecoveryRetry
- RecoveryRetryRequest
- RecoveryRetryResult
- RecoveryRetryFailure
- RecoveryRetryPolicy
- RecoveryRetryOwnership
- RecoveryRetryLifecycle

No public runtime API is introduced by this package. No Python runtime module is introduced by this package.

## Retry Responsibility

RecoveryRetry is a reserved future ownership boundary for describing requested retries of future Runtime Recovery execution attempts after eligible failures.

Package 263 defines responsibility only. It does not implement retry behavior.

Reserved responsibilities:

- describe future retry requests and results
- classify future RecoveryRetryFailure data
- preserve retry eligibility rules
- preserve retry limit rules
- preserve retry ordering rules
- preserve retry backoff semantics
- preserve terminal failure rules
- preserve Runtime Recovery Execution Plan Contract v1 compatibility
- preserve Runtime Recovery Executor Contract v1 compatibility
- preserve Runtime Recovery State Transition Contract v1 compatibility
- preserve Runtime Recovery Checkpoint Contract v1 compatibility
- preserve Runtime Recovery Rollback Contract v1 compatibility

## Ownership Boundaries

RecoveryRetryOwnership owns, in a future implementation package only:

- retry request shape
- retry result shape
- retry failure shape
- retry policy compatibility
- retry lifecycle reporting
- retry eligibility vocabulary
- retry limit vocabulary
- retry ordering vocabulary
- retry backoff vocabulary
- terminal failure vocabulary

RecoveryRetryOwnership does not own in Package 263:

- retry implementation
- rollback implementation
- checkpoint implementation
- state transition implementation
- runtime execution
- recovery execution
- gateway behavior
- executor behavior
- planner behavior
- scheduler behavior
- TaskRunner behavior
- operator behavior
- dispatcher behavior
- supervisor behavior
- native runtime behavior
- watchdog behavior
- persistence
- audit
- journal
- endpoint invocation
- hook registration
- bridge wiring
- subprocess behavior
- filesystem mutation
- runtime state mutation

## Retry Eligibility

RecoveryRetryPolicy reserves these retry eligibility rules:

- retry eligibility is disabled in Package 263
- retry eligibility requires a future explicit GO-reviewed implementation package
- retry requires a future RecoveryExecutionPlan reference
- retry requires a future RecoveryExecutor reference
- retry may reference RecoveryCheckpoint data only as contract data
- retry may reference RecoveryRollback data only as contract data
- retry must not be eligible after terminal failure
- retry must not be eligible after terminal success
- retry must not be eligible when recovery is denied, blocked, or cancelled without a future GO-reviewed unblock policy
- retry eligibility must not bypass Runtime Recovery Gateway admission
- retry eligibility must not bypass Runtime Authorization

Package 263 does not evaluate retry eligibility at runtime.

## Retry Limits

Retry limit rules:

- max_retry_attempts is reserved contract data
- retry_attempt_index must be deterministic in future data
- retry_attempt_index must not exceed max_retry_attempts
- retry limits must be evaluated before any future retry execution
- retry limit exhaustion must produce terminal failure contract data
- retry limits must not be bypassed by RecoveryExecutor, RecoveryRollback, or RecoveryStateTransition

Package 263 does not count retry attempts at runtime.

## Retry Ordering

Retry ordering rules:

- retry attempts must be ordered deterministically in future data
- retry attempts must preserve RecoveryExecutionPlan stage ordering
- retry attempts must not reorder checkpoint lineage
- retry attempts must not reorder rollback target lineage
- retry attempts must not run concurrently unless a future explicit GO-reviewed concurrency contract permits it
- retry ordering must not authorize scheduling, dispatch, endpoint invocation, hook registration, bridge calls, subprocess, filesystem mutation, or runtime state mutation

Package 263 does not order or schedule retry attempts at runtime.

## Retry Backoff Semantics

RecoveryRetryPolicy reserves these backoff semantics:

- backoff_status: "reserved"
- backoff_enabled: false
- backoff_strategy: "none"
- backoff_delay_ms: 0
- backoff_jitter_enabled: false
- timer_scheduled: false

Package 263 does not schedule timers, sleep, wait, spawn subprocesses, invoke endpoints, register hooks, or mutate runtime state.

## Terminal Failure Rules

Terminal failure rules:

- terminal failure must stop future retry eligibility
- terminal failure must not trigger rollback unless a future explicit GO-reviewed policy permits it
- terminal failure must not apply state transitions in Package 263
- terminal failure must not mutate executor state in Package 263
- terminal failure must not mutate runtime state
- terminal failure must not write persistence, audit, or journal data
- terminal failure must not invoke endpoints, register hooks, call bridges, spawn subprocesses, or mutate files

Package 263 does not classify or apply terminal failure at runtime.

## Retry Input

RecoveryRetryRequest is reserved plain data only.

Required fields:

- contract_name: "RecoveryRetryRequest"
- contract_version: "v1"
- retry_request_id
- recovery_execution_plan_id
- executor_request_id
- state_transition_request_id
- checkpoint_id
- rollback_request_id
- retry_attempt_index
- max_retry_attempts
- retry_policy_name
- metadata

Package 263 does not construct or consume RecoveryRetryRequest at runtime.

## Retry Output

RecoveryRetryResult is reserved plain data only.

Required fields:

- contract_name: "RecoveryRetryResult"
- contract_version: "v1"
- retry_result_id
- retry_request_id
- retry_attempt_index
- retry_allowed
- retry_scheduled
- retry_applied
- terminal_failure
- runtime_state_mutated
- failure
- metadata

Package 263 does not produce RecoveryRetryResult at runtime.

## Interaction With RecoveryExecutionPlan

Future RecoveryRetry implementations may reference RecoveryExecutionPlan data only after an explicit GO review.

Package 263 does not call, import, execute, mutate, or wire RecoveryExecutionPlan implementation. RecoveryExecutionPlan remains a contract artifact.

Future interaction rules:

- RecoveryRetry must not create a RecoveryExecutionPlan.
- RecoveryRetry must not reorder RecoveryExecutionPlan stages.
- RecoveryRetry must not alter RecoveryExecutionPlan execution units.
- RecoveryRetry must not alter RecoveryExecutionRetryPolicy in Package 263.
- RecoveryRetry must not bypass Runtime Recovery Gateway admission.

## Interaction With RecoveryExecutor

Future RecoveryRetry implementations may reference RecoveryExecutor data only after an explicit GO review.

Package 263 does not call, import, execute, mutate, or wire RecoveryExecutor implementation. RecoveryExecutor remains a contract artifact.

Future interaction rules:

- RecoveryRetry must not start RecoveryExecutor.
- RecoveryRetry must not stop RecoveryExecutor.
- RecoveryRetry must not retry RecoveryExecutor in Package 263.
- RecoveryRetry must not mark recovery executed.
- RecoveryRetry must not mutate executor state.
- RecoveryRetry must not bypass Runtime Authorization.

## Interaction With RecoveryStateTransition

Future RecoveryRetry implementations may reference RecoveryStateTransition data only after an explicit GO review.

Package 263 does not call, import, execute, mutate, or wire RecoveryStateTransition implementation. RecoveryStateTransition remains a contract artifact.

Future interaction rules:

- RecoveryRetry must not apply state transitions.
- RecoveryRetry must not alter allowed recovery states.
- RecoveryRetry must not override forbidden state transitions.
- RecoveryRetry must not mark a transition applied.
- RecoveryRetry must not mutate runtime state through state-transition behavior.

## Interaction With RecoveryCheckpoint

Future RecoveryRetry implementations may reference RecoveryCheckpoint data only after an explicit GO review.

Package 263 does not call, import, execute, mutate, restore, or wire RecoveryCheckpoint implementation. RecoveryCheckpoint remains a contract artifact.

Future interaction rules:

- RecoveryRetry must not create checkpoints.
- RecoveryRetry must not validate checkpoints at runtime in Package 263.
- RecoveryRetry must not restore checkpoints at runtime in Package 263.
- RecoveryRetry must not mutate checkpoint identity fields.
- RecoveryRetry must not mutate checkpoint lineage fields.

## Interaction With RecoveryRollback

Future RecoveryRetry implementations may reference RecoveryRollback data only after an explicit GO review.

Package 263 does not call, import, execute, mutate, apply, or wire RecoveryRollback implementation. RecoveryRollback remains a contract artifact.

Future interaction rules:

- RecoveryRetry must not apply rollback.
- RecoveryRetry must not select rollback targets.
- RecoveryRetry must not bypass rollback eligibility.
- RecoveryRetry must not mutate rollback result data.
- RecoveryRetry must not mutate runtime state through rollback behavior.

## Lifecycle

RecoveryRetryLifecycle is reserved plain data only.

Reserved lifecycle status values:

- reserved
- requested
- blocked
- denied
- eligible_future_only
- scheduled_future_only
- applied_future_only
- terminal_failure_future_only
- failed_future_only

Package 263 does not transition lifecycle state and does not implement lifecycle behavior.

## Failure Taxonomy

Reserved failure codes:

- recovery_retry_not_implemented
- recovery_retry_disabled
- retry_request_invalid
- retry_not_eligible
- retry_limit_exhausted
- retry_order_invalid
- retry_backoff_forbidden
- terminal_failure_reached
- recovery_execution_plan_reference_invalid
- recovery_executor_reference_invalid
- recovery_state_transition_reference_invalid
- recovery_checkpoint_reference_invalid
- recovery_rollback_reference_invalid
- gateway_bypass_forbidden
- authorization_bypass_forbidden
- executor_start_forbidden
- executor_stop_forbidden
- executor_retry_forbidden
- state_transition_apply_forbidden
- checkpoint_restore_forbidden
- rollback_apply_forbidden
- runtime_wiring_forbidden
- runtime_state_mutation_forbidden
- persistence_forbidden
- audit_forbidden
- journal_forbidden
- endpoint_invocation_forbidden
- hook_registration_forbidden
- bridge_call_forbidden
- subprocess_forbidden
- filesystem_mutation_forbidden

These names classify future retry failures only. They do not authorize retry execution, rollback execution, checkpoint restore, recovery execution, persistence, audit, journal, endpoint invocation, hook registration, bridge calls, subprocess, filesystem mutation, or runtime mutation.

## Compatibility Policy

Runtime Recovery Retry Contract v1 is append-only once sealed.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version, such as Runtime Recovery Retry Contract v2.

Existing v1 fields, retry eligibility rules, retry limit rules, retry ordering rules, retry backoff semantics, terminal failure rules, and failure codes must not be removed, renamed, reordered when order is semantically declared, or assigned new meanings.

## Dependency Graph

Allowed future dependency direction:

```text
Runtime Recovery Gateway
  -> Runtime Recovery Execution Contract v1
  -> Runtime Recovery Execution Plan Contract v1
  -> Runtime Recovery Executor Contract v1
  -> Runtime Recovery State Transition Contract v1
  -> Runtime Recovery Checkpoint Contract v1
  -> Runtime Recovery Rollback Contract v1
  -> Runtime Recovery Retry Contract v1
  -> Future Runtime Recovery Retry Implementation after GO review
```

Forbidden dependency direction:

```text
Runtime Recovery Retry Contract v1
  -> recovery bridge
  -> recovery executor implementation
  -> recovery adapter
  -> recovery integration
  -> planner
  -> scheduler
  -> TaskRunner
  -> operator
  -> dispatcher
  -> supervisor
  -> native runtime
  -> watchdog
  -> persistence
  -> audit
  -> journal
  -> endpoint invocation
  -> hook registration
  -> bridge calls
  -> subprocess
  -> filesystem mutation
  -> runtime state mutation
```

The contract must not call or import existing recovery bridge, executor, adapter, or integration modules.

## Future Implementation Ownership

Future retry implementation packages may implement RecoveryRetry only after explicit GO review.

Future implementation ownership must preserve:

- RecoveryRetry compatibility
- RecoveryRetryRequest compatibility
- RecoveryRetryResult compatibility
- RecoveryRetryFailure compatibility
- RecoveryRetryPolicy compatibility
- RecoveryRetryOwnership compatibility
- RecoveryRetryLifecycle compatibility
- Runtime Recovery Gateway admission precedence
- Runtime Recovery Execution Plan Contract v1 compatibility
- Runtime Recovery Executor Contract v1 compatibility
- Runtime Recovery State Transition Contract v1 compatibility
- Runtime Recovery Checkpoint Contract v1 compatibility
- Runtime Recovery Rollback Contract v1 compatibility
- no direct bypass of Runtime Recovery Gateway
- no direct bypass of Runtime Authorization
- no retry eligibility, limit counting, ordering, backoff scheduling, terminal failure application, or retry application before explicit GO review

Package 263 grants no retry authority.

## Forbidden Implementation Behaviors

Package 263 is Contract/documentation only.

Package 263 must not create runtime modules.

Package 263 must not implement retry behavior.

Package 263 must not modify runtime code.

Package 263 must not modify gateway code.

Package 263 must not modify executor code.

Package 263 must not implement state transition behavior.

Package 263 must not implement checkpoint behavior.

Package 263 must not implement rollback behavior.

Package 263 must not wire recovery runtime modules.

Package 263 must not call or import existing recovery bridge, executor, adapter, or integration modules.

Package 263 must not add public runtime APIs.

Package 263 must not add persistence.

Package 263 must not spawn subprocesses.

Package 263 must not perform filesystem mutation.

Package 263 must not invoke endpoints.

Package 263 must not register hooks.

Package 263 must not mutate runtime state.

Final decision: GO.

Next package: Package 264.
