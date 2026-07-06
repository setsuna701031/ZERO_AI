# Limited Active Runtime Opening Gate Contract v1

Status: disabled / limited-runtime-opening-gate-review-only.

Schema: `zero.runtime.limited_active_runtime_opening_gate.v1`.

This contract reserves the limited active runtime opening gate review layer. It builds on the controlled
activation commit gate review layer. It is deterministic and data-only. It does not allow runtime opening,
limited runtime session creation, execution lease activation, capability scope commit, live watchdog, live
rollback, live shutdown, activation, runtime mode transition, execution, mutation, external IO, network IO,
unbounded autonomy, or self-start.

Required request fields:

- runtime_opening_gate_id
- commit_gate_id
- candidate_id
- activation_attempt_id
- operator_id
- executor_id
- commit_gate_evidence
- runtime_session_container
- limited_execution_lease
- capability_scope
- step_budget_and_watchdog
- live_rollback_and_shutdown
- audit_required

Hard boundary values:

- runtime_open_allowed=false
- limited_runtime_session_created=false
- execution_lease_active=false
- capability_scope_committed=false
- watchdog_live=false
- rollback_live=false
- shutdown_live=false
- activation_allowed=false
- runtime_mode_transition_allowed=false
- execution_allowed=false
- mutation_allowed=false
- external_io_allowed=false
- autonomy_allowed=false
- self_start_allowed=false

Non-mainline issue reporting remains required. Any detected non-mainline issue must be represented in output,
not silently skipped.

Final decision: GO for limited active runtime opening gate contract review only.
