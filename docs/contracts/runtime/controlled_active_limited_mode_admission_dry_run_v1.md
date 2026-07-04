# Controlled Active Limited Mode Admission Dry-Run Contract v1

Status: disabled / admission-dry-run-only.

This contract reserves the controlled active limited mode admission dry-run layer.

It does not grant admission, commit approval, verify ownership as live state, transition runtime mode,
enable controlled active mode, mutate runtime state, mutate files, execute tools, access network IO,
start autonomy, or self-start.

Required request fields:

- request_id
- candidate_id
- activation_attempt_id
- operator_id
- requested_mode
- source_layer
- admission_scope
- ownership_verification
- operator_approval
- state_dry_run_review
- boundary_locks
- audit_required

Non-mainline issue reporting remains required. Any issue detected outside the mainline scope must be reported,
not silently skipped.

Final decision: GO for admission dry-run contract only.
