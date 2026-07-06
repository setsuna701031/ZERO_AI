# Controlled Active Limited Mode Final Readiness Contract v1

Status: disabled / final-readiness-dry-run-only.

Schema: `zero.runtime.controlled_active_limited_mode_final_readiness.v1`.

This contract reserves the final readiness dry-run layer for controlled active limited mode. It is data-only
and does not allow real activation, runtime mode transition, execution, runtime mutation, file mutation,
external tool execution, network IO, unbounded autonomy, or self-start.

Required request fields:

- readiness_id
- candidate_id
- activation_attempt_id
- operator_id
- executor_id
- previous_seals
- ownership_chain
- readiness_candidate
- safety_boundary_matrix
- go_candidate_evidence
- audit_required

Missing required fields must be rejected.

Required previous seals:

- controlled_activation_gate_review
- controlled_active_limited_mode_candidate
- controlled_active_limited_mode_state_dry_run
- controlled_active_limited_mode_admission_dry_run
- controlled_active_limited_mode_execution_dry_run

Each previous seal must be present, closed, and sealed. Missing, open, or unsealed prior seals block readiness.

Ownership chain review is preview-only. `ownership_verified` remains false and `ownership_commit_allowed`
remains false.

Activation readiness candidate evidence may set `activation_ready_candidate=true` only as preview evidence.
`activation_allowed`, `activation_commit_allowed`, and `runtime_mode_transition_allowed` remain false.

GO candidate evidence may set `go_candidate_created=true` only as evidence. `go_allowed`,
`activation_allowed`, and `execution_allowed` remain false.

Non-mainline issue reporting remains required. Any detected non-mainline issue must be represented in output,
not silently skipped.

Final decision: GO for final readiness dry-run contract only.
