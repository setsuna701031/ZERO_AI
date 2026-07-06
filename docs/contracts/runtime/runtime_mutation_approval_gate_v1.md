# Runtime Mutation Approval Gate v1

## Purpose
Runtime Mutation Approval Gate introduces an explicit approval or denial record between write planning and any future mutation execution.

This contract creates approval records only. Approval does not execute mutation.

## Required Inputs
- `mutation_approval_request_id`
- `runtime_session_id`
- `execution_lease`
- `capability_grant`
- `executor_binding`
- `read_verification`
- `write_plan`
- `approval_input`
- `audit_required`

## Required Chain
- Runtime session id must be present.
- Execution lease must be granted for the same runtime session.
- Capability grant must be granted for the same runtime session and lease.
- Capability grant must include `mutation_access: true`.
- Executor binding must be bound to the same session, lease, and grant.
- Read replay verification must be verified.
- Read evidence must not be stale, mismatched, expired, revoked, or invalid.
- Write plan must exist.
- Write plan status must be `planned`.
- Write plan must point to the verified read replay record.
- Explicit approval input or explicit denial input must be present.

## Approval Record
Required fields:
- `mutation_approval_id`
- `write_plan_id`
- `runtime_session_id`
- `approval_status`
- `approved_operation`
- `target_resource`
- `expected_previous_digest`
- `approval_reason`
- `denial_reason`
- `rollback_required`
- `audit_projection`

## Status
- `approved`
- `denied`
- `expired`
- `revoked`

## Rules
- `approved` creates approval evidence only.
- `approved` does not execute mutation.
- `denied` blocks mutation readiness.
- `expired` blocks mutation readiness.
- `revoked` blocks mutation readiness.
- mismatch or stale evidence blocks approval.

## Forbidden Effects
- no file write
- no append
- no delete
- no rename
- no chmod
- no subprocess
- no shell
- no network
- no actual mutation
- no task execution
- no autonomy
- no background loop

## Decision
GO for mutation approval and denial records only. Runtime mutation remains forbidden.
