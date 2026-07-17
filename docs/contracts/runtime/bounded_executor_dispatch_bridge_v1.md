# Bounded Executor Dispatch Bridge v1

## Package
1417-1424: Bounded Executor Dispatch Bridge Bundle

## Purpose
Defines the governed bridge from RuntimeTickResult to one BoundedExecutorDispatchRequest.

The bridge only emits a dispatch request when the tick status is ALLOW_SINGLE_TICK and lease, grant, and executor binding authority are present. It may set execution_requested to true, but actual_executor_called remains false.

## Input
- RuntimeTickResult

## Output
BoundedExecutorDispatchRequest

## Dispatch Fields
- dispatch_request_id
- source_tick_id
- source_cycle_id
- tick_status
- requested_action
- dispatch_status
- execution_lease_id
- capability_grant_id
- executor_binding_id
- execution_requested
- actual_executor_called
- blocked_reason

## Dispatch Rule
- ALLOW_SINGLE_TICK with lease, grant, and binding creates dispatch_requested.
- Recovery, paused, closed, stopped, blocked, missing, or unsupported ticks do not dispatch.
- Missing authority blocks dispatch.

## Locked Surfaces
- direct executor call
- scheduler import or call
- loop
- thread
- automatic retry
- ungoverned execution

## Contract Rule
Bounded Executor Dispatch Bridge is dispatch-request-only. The same RuntimeTickResult must produce the same BoundedExecutorDispatchRequest.
