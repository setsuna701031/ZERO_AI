# Runtime Controlled Mutation Execution Audit

## Audit Scope
Runtime Controlled Mutation Execution performs controlled `create` and `replace` operations only after approved mutation evidence.

## Required Evidence
- runtime session id
- granted execution lease
- granted capability record
- mutation capability flag
- bound executor record
- verified read replay record
- planned write plan record
- approved mutation approval record
- expected previous digest match
- rollback metadata

## Blocking Evidence
Execution is blocked for:
- missing approval
- denied approval
- expired approval
- revoked approval
- digest mismatch
- missing rollback metadata
- unsupported operation
- delete operation
- direct write bypass
- boundary unlock attempts

## Mutation Evidence
Successful execution records:
- `before_digest`
- `after_digest`
- `rollback_record`
- `evidence_after_mutation`
- `mutation_ownership_audit`
- controlled executor usage

## Forbidden Surface Evidence
Every execution, audit, projection, and seal record reports:
- `delete_performed: False`
- `rename_performed: False`
- `chmod_performed: False`
- `shell_started: False`
- `subprocess_started: False`
- `network_performed: False`
- `uncontrolled_write_performed: False`
- `direct_filesystem_bypass_performed: False`
- `autonomy_started: False`
- `background_loop_started: False`

## Audit Decision
The audit decision is `reserved_runtime_controlled_mutation_execution`.

ZERO can perform the first controlled state mutation with evidence and rollback ownership.
