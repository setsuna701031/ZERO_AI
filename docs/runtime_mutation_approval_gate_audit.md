# Runtime Mutation Approval Gate Audit

## Audit Scope
Runtime Mutation Approval Gate records explicit approval, denial, expiration, and revocation evidence for a planned mutation. It does not perform the planned operation.

## Required Evidence
- runtime session id
- granted execution lease
- granted capability record
- mutation capability flag
- bound executor record
- verified read replay record
- planned write plan record
- explicit approval or denial input

## Denial Evidence
The approval validator records denial reasons for:
- missing write plan
- invalid runtime session
- inactive lease
- inactive capability grant
- inactive executor binding
- missing mutation capability
- missing verified read evidence
- stale or mismatched evidence
- digest mismatch
- write plan not planned
- missing explicit approval or denial input
- boundary unlock attempts

## Effect Evidence
Every validation, approval, audit, projection, and seal record reports:
- `filesystem_mutation_performed: False`
- `file_write_performed: False`
- `append_performed: False`
- `delete_performed: False`
- `rename_performed: False`
- `chmod_performed: False`
- `subprocess_started: False`
- `shell_started: False`
- `network_performed: False`
- `task_executed: False`
- `autonomy_started: False`
- `background_loop_started: False`

## Audit Decision
The audit decision is `reserved_runtime_mutation_approval_gate_record_only`.

ZERO can approve a planned mutation, but still cannot mutate anything.
