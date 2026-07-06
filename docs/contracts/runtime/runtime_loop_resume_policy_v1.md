# Runtime Loop Resume Policy v1

## Package
1393-1400: Runtime Loop Resume Policy Bundle

## Purpose
Defines the governed resume decision layer above Runtime Progress Memory.

The layer consumes a runtime progress snapshot and resume cursor, then emits a deterministic resume decision. It does not execute a step, call an executor, call a scheduler, mutate progress memory, start a background loop, or retry automatically.

## Flow
Progress Memory
      ->
Resume Cursor
      ->
Resume Policy Decision

## Inputs
- RuntimeProgressSnapshot
- ResumeCursor

## Output
RuntimeResumeDecision

## Decision Fields
- decision_id
- action
- next_step
- recovery_required
- reason

## Supported Actions
- CONTINUE_EXECUTION
- WAIT_FOR_INPUT
- ENTER_RECOVERY
- MARK_COMPLETE
- BLOCKED

## Decision Rules
- COMPLETE cursor state produces MARK_COMPLETE.
- BLOCKED cursor state produces BLOCKED.
- RECOVERY_REQUIRED cursor state or recovery-required snapshot produces ENTER_RECOVERY.
- WAITING cursor state produces WAIT_FOR_INPUT.
- CONTINUE cursor state produces CONTINUE_EXECUTION.
- Unknown cursor state produces WAIT_FOR_INPUT.

## Locked Surfaces
- step execution
- executor calls
- scheduler calls
- progress memory mutation
- background loop start
- automatic retry

## Contract Rule
Resume policy is decision-only. The same progress snapshot and resume cursor must produce the same resume decision.
