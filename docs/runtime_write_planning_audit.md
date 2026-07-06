# Runtime Write Planning Audit

## Audit Scope
Runtime Write Planning is an audit-visible record factory for future write intent. It does not perform the planned operation.

## Required Evidence
- runtime session id
- granted execution lease
- granted capability record
- mutation capability flag
- bound executor record
- verified read replay record
- digest match between read evidence and expected previous digest

## Denial Evidence
The write plan validator records denial reasons for:
- missing read verification
- stale or mismatched read verification
- invalid runtime session
- inactive lease
- inactive capability grant
- missing mutation capability
- inactive executor binding
- unsupported operation
- missing target resource
- missing planned digest
- boundary unlock attempts

## Effect Evidence
Every validation, plan, audit, projection, and seal record reports:
- `filesystem_mutation_performed: False`
- `file_write_performed: False`
- `open_write_performed: False`
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
The audit decision is `reserved_runtime_write_planning_plan_only`.

ZERO can decide how it would modify a resource, but cannot perform mutation.
