# Runtime Task Execution Admission v1

## Purpose
Runtime Task Execution Admission introduces an admission gate for task execution after controlled mutation recovery.

This layer creates task admission records only. It does not execute tasks, start loops, invoke executors, spawn processes, run shell commands, perform network IO, or mutate runtime state.

## Required Inputs
- `runtime_session_id`
- `execution_lease`
- `capability_grant`
- `executor_binding`
- `tool_boundary`
- `tool_invocation`
- `requested_task_id`
- `requested_task_type`
- `authorization_input`
- `audit_required`

## Required Chain
- Runtime session id must be present.
- Execution lease must be granted for the same runtime session.
- Capability grant must be granted for the same runtime session and lease.
- Executor binding must be bound to the same session, lease, and grant.
- Tool boundary must be admitted for the same session, lease, grant, and binding.
- Tool invocation must be approved for the same session, lease, grant, binding, and tool boundary.
- Mutation task admission requires mutation recovery readiness when mutation was performed.
- Stale, expired, revoked, or failed evidence blocks admission.

## Task Admission Record
Required fields:
- `task_admission_id`
- `runtime_session_id`
- `execution_lease_id`
- `capability_grant_id`
- `executor_binding_id`
- `requested_task_id`
- `requested_task_type`
- `admission_status`
- `denial_reason`
- `recovery_required`
- `audit_projection`

## Supported Task Types
- `read_task`
- `write_task`
- `mutation_task`
- `recovery_task`

## Supported Status
- `admitted`
- `denied`
- `expired`
- `revoked`

## Rules
- Admitted means record admitted only.
- Admitted does not execute the task.
- Mutation task requires recovery readiness.
- Missing lease, capability, executor, tool boundary, or tool invocation blocks admission.
- Stale evidence blocks admission.

## Forbidden
- task execution
- subprocess
- shell
- network
- uncontrolled mutation
- autonomy
- self-start
- background loop

## Decision
GO for task execution admission records only.
