# Controlled Active Limited Mode Final Switch Authority Contract v1

Status: disabled / final-switch-authority-review-only.

Schema: `zero.runtime.controlled_active_limited_mode_final_switch_authority.v1`.

This contract reserves the final switch authority review layer. It is deterministic and data-only. It does
not allow real activation, final switch enablement, runtime mode transition, execution, mutation, external
tool execution, network IO, unbounded autonomy, or self-start.

Required request fields:

- switch_authority_id
- readiness_id
- candidate_id
- activation_attempt_id
- operator_id
- executor_id
- operator_confirmation_token
- rollback_authority
- kill_switch_authority
- bounded_runtime_lease
- controlled_activation_transaction
- audit_required

Missing required fields must be rejected.

Hard boundary values:

- activation_allowed=false
- final_switch_allowed=false
- runtime_mode_transition_allowed=false
- execution_allowed=false
- mutation_allowed=false
- external_io_allowed=false
- autonomy_allowed=false
- self_start_allowed=false

Operator confirmation token review is preview-only. Rollback authority and kill switch authority live
readiness are preview-only. Bounded runtime lease and controlled activation transaction are preview-only.

Non-mainline issue reporting remains required. Any detected non-mainline issue must be represented in output,
not silently skipped.

Final decision: GO for final switch authority contract review only.
