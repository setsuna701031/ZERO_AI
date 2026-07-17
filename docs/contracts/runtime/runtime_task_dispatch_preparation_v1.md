# Runtime Task Dispatch Preparation v1

## Purpose
Runtime Task Dispatch Preparation prepares admitted runtime tasks for executor dispatch.

This layer creates dispatch preparation records only. It does not execute executors, invoke tools, spawn processes, run shells, perform network IO, mutate files, mutate runtime state, complete tasks, start autonomy loops, or start background workers.

## Required Inputs
- `task_admission_id`
- `runtime_session_id`
- `execution_lease_id`
- `executor_binding_id`
- `capability_grant_id`

The implementation receives these through:
- admitted task admission record
- execution lease record
- capability grant record
- executor binding record

## Dispatch Preparation Record
Required fields:
- `dispatch_id`
- `task_admission_id`
- `executor_binding_id`
- `dispatch_status`
- `dispatch_plan`
- `executor_target`
- `preparation_time`
- `denial_reason`
- `audit_record`

## Statuses
- `prepared`
- `denied`
- `expired`
- `revoked`

## Rules
- Denied admission cannot prepare dispatch.
- Expired lease blocks dispatch preparation.
- Revoked capability blocks dispatch preparation.
- Missing executor binding blocks preparation.
- Prepared dispatch cannot execute.
- Prepared dispatch cannot invoke tools.
- Prepared dispatch cannot mutate state.

## Forbidden
- `executor.run()`
- subprocess
- shell
- network
- filesystem mutation
- task completion
- autonomy loop
- background worker

## Decision
GO for dispatch preparation records only.
