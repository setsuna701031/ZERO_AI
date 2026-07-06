# Runtime Mutation Recovery Audit

## Audit Scope
Runtime Mutation Recovery records recovery planning and controlled restore evidence for resources mutated by Runtime Controlled Mutation Execution.

## Required Audit Evidence
- `mutation_recovery_id`
- `mutation_execution_id`
- rollback source
- recovery status
- restored digest
- recovery reason
- failure reason
- audit projection

## Integrity Evidence
The audit projection records:
- rollback integrity verification
- ownership chain validation
- recovery audit evidence
- unrelated resource modification blocked

## Forbidden Surface Evidence
Every recovery record, audit record, projection, and seal reports:
- `arbitrary_write_performed: False`
- `arbitrary_delete_performed: False`
- `rename_performed: False`
- `chmod_performed: False`
- `shell_started: False`
- `subprocess_started: False`
- `network_performed: False`
- `executor_task_executed: False`
- `autonomy_started: False`
- `background_loop_started: False`

## Audit Decision
The audit decision is `reserved_runtime_mutation_recovery`.

ZERO can recover controlled state only through verified rollback ownership.
