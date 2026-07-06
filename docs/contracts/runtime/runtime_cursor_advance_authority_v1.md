# Runtime Cursor Advance Authority v1

## Package
1521-1528: Runtime Cursor Advance Authority

## Purpose
Authorizes cursor movement after a valid RuntimeProgressApplyRecord.

This layer produces a cursor advance decision only. It does not start the next tick, call the scheduler, call the executor, or mutate runtime state directly.

## Input
RuntimeProgressApplyRecord

## Output
RuntimeCursorAdvanceRecord

## Required Fields
- cursor_advance_authorized
- previous_cursor
- next_cursor
- source_progress_id
- denial_reason
- runtime_state_mutated

## Rules
- cursor advance requires valid apply authorization
- missing progress record denies cursor advance
- rejected progress record denies cursor advance
- missing next candidate denies cursor advance
- denied records must be deterministic
- previous_cursor is preserved
- next_cursor is assigned only when cursor_advance_authorized is true
- runtime_state_mutated remains false

## Locked Surfaces
- task execution
- scheduler call
- executor call
- runtime queue mutation
- progress memory mutation
- loop start or continuation
- next tick request

## Contract Rule
Runtime Cursor Advance Authority decides the next cursor position only. Scheduler admission and task execution remain downstream responsibilities.
