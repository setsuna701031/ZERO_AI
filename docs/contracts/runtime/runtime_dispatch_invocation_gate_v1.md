# Runtime Dispatch Invocation Gate v1

## Package
1441-1448: Runtime Dispatch Invocation Gate Bundle

## Purpose
Creates the final authority gate before executor-facing invocation.

The gate converts a ControlledLoopPlanExecutionRecord into a RuntimeInvocationPermit. It still does not call an executor.

## Input
- ControlledLoopPlanExecutionRecord
- lease/grant/binding authority

## Output
RuntimeInvocationPermit

## Fields
- permit_id
- source_execution_record_id
- invocation_allowed
- executor_permission
- dispatch_reference
- denial_reason
- authority_verified

## Allow Rule
Invocation is allowed only when:
- execution_status is ONE_TICK_SELECTED
- lease authority is present
- grant authority is present
- binding authority is present

## Locked Surfaces
- executor import or call
- scheduler import or call
- step execution
- progress mutation
- loop continuation
- automatic retry
- thread creation

## Contract Rule
Runtime Dispatch Invocation Gate is permit-only. The same execution record and authority must produce the same RuntimeInvocationPermit.
