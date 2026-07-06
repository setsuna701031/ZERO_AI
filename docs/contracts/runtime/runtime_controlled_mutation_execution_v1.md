# Runtime Controlled Mutation Execution v1

## Purpose
Runtime Controlled Mutation Execution introduces the first real controlled state mutation path.

Execution is limited to approved `create` and `replace` operations through `core/runtime/runtime_controlled_mutation_execution.py`.

## Required Inputs
- `mutation_execution_request_id`
- `runtime_session_id`
- `execution_lease`
- `capability_grant`
- `executor_binding`
- `read_verification`
- `write_plan`
- `mutation_approval`
- `workspace_root`
- `mutation_payload`
- `audit_required`

## Required Chain
- Runtime session id must be present.
- Execution lease must be granted for the same runtime session.
- Capability grant must be granted for the same runtime session and lease.
- Capability grant must include `mutation_access: true`.
- Executor binding must be bound to the same session, lease, and grant.
- Read replay verification must be verified.
- Write plan must be planned.
- Mutation approval must be approved.
- Expected previous digest must match read evidence, write plan, approval, and current resource digest.
- Rollback metadata must exist before mutation.
- Controlled mutation executor path must be authorized.

## Execution Record
Required fields:
- `mutation_execution_id`
- `mutation_approval_id`
- `target_resource`
- `operation`
- `before_digest`
- `after_digest`
- `execution_status`
- `rollback_record`
- `failure_reason`
- `audit_projection`

## Allowed Operations
- `create`
- `replace`

## Forbidden
- delete
- rename
- chmod
- shell
- subprocess
- network
- uncontrolled write
- direct filesystem mutation bypass
- autonomy
- background loop

## Required Safety
- verify digest before mutation
- create rollback snapshot metadata
- use controlled mutation executor path
- record evidence after mutation
- record mutation ownership audit

## Decision
GO for controlled create and replace mutation execution only.
