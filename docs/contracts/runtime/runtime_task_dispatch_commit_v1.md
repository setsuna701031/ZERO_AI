# Runtime Task Dispatch Commit v1

## Purpose

Runtime Task Dispatch Commit v1 commits a prepared runtime task dispatch into a dispatch-ready record. It is the commit gate after Runtime Task Dispatch Preparation and before any future executor invocation boundary.

This contract is record-only. A committed dispatch is not execution authority.

## Schema

`zero.runtime.task_dispatch_commit.v1`

## Required Inputs

- `dispatch_commit_request_id`
- `dispatch_preparation`
- `runtime_session_id`
- `execution_lease`
- `capability_grant`
- `executor_binding`
- `audit_required`

## Commit Record Fields

- `dispatch_commit_id`
- `dispatch_id`
- `task_admission_id`
- `runtime_session_id`
- `execution_lease_id`
- `capability_grant_id`
- `executor_binding_id`
- `executor_target`
- `commit_status`
- `commit_reason`
- `commit_time`
- `denial_reason`
- `audit_record`

## Statuses

- `committed`
- `denied`
- `expired`
- `revoked`

## Gates

A commit requires:

- a prepared dispatch record
- active granted execution lease
- active granted capability grant
- active bound executor binding
- matching executor target metadata
- locked forbidden surfaces
- audit requirement
- non-mainline issue reporting requirement

Denied, expired, revoked, or mismatched dispatch preparation records must not commit.

## Forbidden Surfaces

Runtime Task Dispatch Commit must not:

- call `executor.run()`
- execute tasks
- invoke tools
- start subprocesses
- start shells
- use network
- mutate filesystems
- mutate runtime state
- complete tasks
- start autonomy loops
- start background workers

## Final Decision

GO for dispatch commit records only. Executor execution remains disabled.
