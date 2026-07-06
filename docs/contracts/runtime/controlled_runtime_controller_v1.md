# Controlled Runtime Controller v1

## Package
1401-1408: Controlled Runtime Controller Bundle

## Purpose
Defines the first authorized runtime cycle controller after the Runtime Loop Resume Policy.

The controller consumes a RuntimeResumeDecision and emits a deterministic RuntimeCycleRequest. It requests the next governed runtime cycle action, but it does not execute steps, call executors, call schedulers, mutate progress, retry, create threads, or run a loop.

## Flow
Resume Policy
      ->
Controlled Controller
      ->
Cycle Request

## Input
- RuntimeResumeDecision

## Output
RuntimeCycleRequest

## RuntimeCycleRequest Fields
- cycle_id
- source_decision_id
- requested_action
- next_step_reference
- authorization_required
- execution_requested

## Action Mapping
- CONTINUE_EXECUTION maps to REQUEST_NEXT_TICK.
- ENTER_RECOVERY maps to REQUEST_RECOVERY_FLOW.
- WAIT_FOR_INPUT maps to PAUSE_RUNTIME.
- MARK_COMPLETE maps to CLOSE_RUNTIME.
- BLOCKED maps to STOP_RUNTIME.

## Locked Surfaces
- step execution
- executor imports and calls
- scheduler imports and calls
- while loops
- thread creation
- automatic retry
- progress mutation
- autonomous background execution

## Contract Rule
Controlled Runtime Controller is request-only. The same RuntimeResumeDecision must produce the same RuntimeCycleRequest.
