# Runtime Work Cycle Coordinator v1

## Package
1361-1368: Runtime Work Cycle Coordinator Bundle

## Purpose
Defines the record-only work-cycle coordinator layer after Runtime Loop Controller.

The layer accepts one governed loop controller output plus the required runtime authority chain and returns exactly one controlled work-cycle decision: continue, stop, wait, recover, or deny.

## Required Chain
- runtime_session_id
- execution_lease_id
- capability_grant_id
- executor_binding_id
- loop_controller_id
- execution_tick_id
- task_admission_id
- dispatch_commit_id
- executor_invocation_boundary_id

## Statuses
- coordinated
- blocked
- stopped
- recovery_required
- denied

## Decisions
- continue
- stop
- wait
- recover
- deny

## Locked Surfaces
- executor run
- task execution
- tool invocation
- subprocess
- shell
- network
- filesystem mutation
- state mutation
- task completion
- autonomy loop
- self start
- background worker

## Contract Rule
A work-cycle decision is coordination data only. It never runs an executor, invokes tools, mutates files, completes a task, starts a loop, or bypasses any upstream authority record.
