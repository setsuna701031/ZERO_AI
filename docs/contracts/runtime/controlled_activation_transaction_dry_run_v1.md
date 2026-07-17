# Controlled Activation Transaction Dry-Run Contract v1

Status: disabled / transaction-dry-run-only.

Schema: `zero.runtime.controlled_activation_transaction_dry_run.v1`.

This contract reserves a controlled activation transaction dry-run layer that builds on the final readiness
dry-run and final switch authority review layers. It is deterministic and data-only. It does not allow a real
transaction, transaction commit, activation, runtime mode transition, execution, mutation, external IO,
network IO, unbounded autonomy, or self-start.

Required request fields:

- transaction_dry_run_id
- switch_authority_id
- readiness_id
- candidate_id
- activation_attempt_id
- operator_id
- executor_id
- final_readiness_evidence
- final_switch_authority_review
- transaction_plan
- pre_commit_safety_check
- commit_boundary
- rollback_path
- audit_required

Hard boundary values:

- transaction_allowed=false
- transaction_commit_allowed=false
- activation_allowed=false
- runtime_mode_transition_allowed=false
- execution_allowed=false
- mutation_allowed=false
- external_io_allowed=false
- autonomy_allowed=false
- self_start_allowed=false

The final readiness and final switch authority inputs must remain closed NO-GO review evidence. Any parent
evidence that attempts to unlock activation, final switch, transition, execution, or mutation blocks the
transaction dry-run.

Non-mainline issue reporting remains required. Any detected non-mainline issue must be represented in output,
not silently skipped.

Final decision: GO for controlled activation transaction dry-run contract only.
