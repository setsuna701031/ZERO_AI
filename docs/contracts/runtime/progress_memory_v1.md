# Runtime Progress Memory v1

## Package
1385-1392: Runtime Progress Memory + Resume Cursor Bundle

## Purpose
Defines the record-only progress projection layer after Runtime Step Result Commit.

The layer consumes step result commit records, projects deterministic runtime progress memory, and calculates a resume cursor. It does not execute work, call an executor, mutate a scheduler, repair automatically, or start a loop.

## Flow
Commit History
      ↓
Progress Projection
      ↓
Resume Cursor

## Progress Snapshot Fields
- runtime_id
- completed_steps
- failed_steps
- skipped_steps
- last_committed_step
- resume_cursor
- recovery_required

## Resume Cursor States
- CONTINUE
- WAITING
- RECOVERY_REQUIRED
- COMPLETE

## Locked Surfaces
- task execution
- executor calls
- scheduler mutation
- autonomous loop
- automatic repair

## Contract Rule
Progress memory is replay projection only. The same commit history must produce the same snapshot and cursor.
