# Runtime Tick Request Gate v1

## Package
1529-1536: Runtime Tick Request Gate

## Purpose
Consumes RuntimeCursorAdvanceRecord records and decides whether a next runtime tick may be requested.

This gate may authorize a tick request record. It may not wake the scheduler, call the scheduler, call the executor, execute a task, mutate runtime state, mutate progress memory, or advance the cursor.

## Input
RuntimeCursorAdvanceRecord

## Output
RuntimeTickRequestRecord

## Required Fields
- tick_request_authorized
- source_cursor_advance_id
- current_cursor
- requested_tick_reason
- denial_reason
- scheduler_invoked
- executor_invoked
- runtime_state_mutated

## Rules
- valid cursor advance authorizes tick request
- missing cursor advance record denies tick request
- rejected cursor advance record denies tick request
- denied records must use deterministic denial reasons
- scheduler_invoked is always false
- executor_invoked is always false
- runtime_state_mutated is always false

## Locked Surfaces
- scheduler wake
- scheduler call
- executor call
- task execution
- runtime state mutation
- progress memory mutation
- cursor advancement

## Contract Rule
Runtime Tick Request Gate creates deterministic tick request authorization data only. Scheduler admission remains downstream work.
