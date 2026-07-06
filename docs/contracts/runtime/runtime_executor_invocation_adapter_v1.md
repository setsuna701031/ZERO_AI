# Runtime Executor Invocation Adapter v1

## Package
1449-1456: Runtime Executor Invocation Adapter Bundle

## Purpose
Defines the final adapter between RuntimeInvocationPermit and executor boundary.

The adapter converts a RuntimeInvocationPermit into a RuntimeExecutorInvocationEnvelope. It still does not execute.

## Input
- RuntimeInvocationPermit

## Output
RuntimeExecutorInvocationEnvelope

## Fields
- envelope_id
- source_permit_id
- executor_target
- invocation_authorized
- payload_reference
- execution_started
- executor_called
- result_expected

## Allow Rule
An envelope is authorized only when:
- invocation_allowed is true
- authority_verified is true
- lease, grant, and binding authority are present

## Locked Surfaces
- executor implementation import
- executor run
- command execution
- file mutation
- progress mutation
- retry scheduling
- loop creation
- thread creation
- scheduler import

## Contract Rule
Runtime Executor Invocation Adapter is envelope-only. The same RuntimeInvocationPermit must produce the same RuntimeExecutorInvocationEnvelope.
