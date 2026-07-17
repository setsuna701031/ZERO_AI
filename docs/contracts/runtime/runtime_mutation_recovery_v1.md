# Runtime Mutation Recovery v1

## Purpose
Runtime Mutation Recovery introduces rollback planning and controlled recovery for resources mutated through Runtime Controlled Mutation Execution.

Recovery is limited to restoring resources that have a successful controlled mutation execution record, rollback record, digest chain, and mutation ownership evidence.

## Required Inputs
- `mutation_execution_id`
- `mutation_execution_record`
- `rollback_record`
- `rollback_source`
- `workspace_root`
- `before_digest`
- `after_digest`
- `mutation_ownership_evidence`
- `recovery_reason`

## Recovery Record
Required fields:
- `mutation_recovery_id`
- `mutation_execution_id`
- `rollback_source`
- `recovery_status`
- `restored_digest`
- `recovery_reason`
- `failure_reason`
- `audit_projection`

## Supported Status
- `planned`
- `restored`
- `failed`
- `denied`

## Required Chain
- Mutation execution id must match the controlled mutation execution record.
- Mutation execution must have succeeded.
- Controlled mutation executor usage must be present.
- Atomic mutation path evidence must be present.
- Rollback record must match mutation execution id.
- Rollback record must match target resource.
- Rollback record must match before and after digests.
- Rollback record must be ready and not already executed.
- Mutation ownership evidence must be verified.
- Ownership approval id must match the mutation execution record.
- Rollback source must target the same resource.
- Restore content digest must match `before_digest`.

## Allowed
- Create a deterministic recovery plan.
- Restore only the resource mutated through controlled mutation execution.
- Remove a created resource only when rollback evidence proves the resource was created by controlled mutation execution.

## Forbidden
- arbitrary write
- arbitrary delete
- rename
- chmod
- subprocess
- shell
- network
- executor task execution
- autonomy
- background loop
- modifying unrelated resources
- bypassing mutation ownership chain

## Required Safety
- rollback integrity verification
- ownership chain validation
- current digest verification before restore
- recovery audit evidence
- forbidden surface reporting on record, audit, projection, and seal

## Decision
GO for controlled mutation recovery only.
