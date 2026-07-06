# Runtime Write Planning v1

## Purpose
Runtime Write Planning creates deterministic write plan records after verified read replay evidence.

This contract is plan-only. It does not write, append, delete, rename, chmod, run commands, use shell, use network, execute tasks, start autonomy, or run background loops.

## Required Inputs
- `write_plan_request_id`
- `runtime_session_id`
- `execution_lease`
- `capability_grant`
- `executor_binding`
- `read_verification`
- `target_resource`
- `planned_operation`
- `expected_previous_digest`
- `planned_digest`
- `audit_required`

## Required Chain
- Runtime session id must be present.
- Execution lease must be granted for the same runtime session.
- Capability grant must be granted for the same runtime session and lease.
- Capability grant must include `mutation_access: true`.
- Executor binding must be bound to the same session, lease, and grant.
- Read replay verification must be `verified`.
- Read replay verification must allow mutation readiness.
- Expected previous digest must match the verified current digest.
- Original and current digest must match.
- Stale, expired, invalid, revoked, or mismatched read evidence blocks planning.

## Supported Operations
- `create`
- `replace`
- `append`
- `delete`

All operations are metadata plans only.

## Write Plan Record
Required fields:
- `write_plan_id`
- `runtime_session_id`
- `source_read_verification_id`
- `target_resource`
- `planned_operation`
- `expected_previous_digest`
- `planned_digest`
- `write_status`
- `denial_reason`
- `audit_projection`

Additional required metadata:
- `mutation_ownership`
- `rollback_preparation`
- `audit_evidence`
- immutable effect flags showing no mutation or execution occurred

## Status
- `planned`
- `denied`
- `expired`
- `revoked`

## Forbidden Effects
- no file write
- no `open(..., "w")`
- no append
- no delete
- no rename
- no chmod
- no subprocess
- no shell
- no network
- no task execution
- no autonomy
- no background loop
- no actual mutation

## Decision
GO for write planning records only. Runtime mutation remains forbidden.
