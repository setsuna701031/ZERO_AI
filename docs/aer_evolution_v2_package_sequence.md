# AER Evolution v2 Package Sequence

## Purpose

This document defines the implementation order for AER Evolution v2 after the mainline design is locked.

The sequence protects RC1 behavior by building v2 foundation surfaces on the separate evolution branch before scheduler or runtime integration begins.

## Foundation Order

1. Package 78 - Mainline Design
2. Package 79 - Operator Lifecycle
3. Package 80 - Checkpoint Model
4. Package 81 - Operator State Machine
5. Package 82 - Operator Execution Context
6. Package 83 - Checkpoint Store
7. Package 84 - Resume Engine
8. Package 85 - Foundation Architecture Review
9. Package 86 - Operator Event Log
10. Package 87 - Audit Reader
11. Package 88 - Checkpoint Store Read Index
12. Package 89 - Audit Snapshot Composition
13. Package 90 - Human Approval Boundary
14. Package 91 - Stop Condition
15. Package 92 - Issue Reporter
16. Package 93 - Long-running Operator Loop
17. Package 94+ - Scheduler / Runtime integration

## Package Boundaries

Packages 78 through 93 define v2 foundation surfaces without changing RC1 scheduler, task runner, or operator runtime behavior.

Scheduler and runtime integration begins only at Package 94 or later.

## Package 90

Package 90 adds the Human Approval Boundary contract for AER v2 without persistence, event emission, UI, operator loop behavior, scheduler integration, or runtime execution.

All future v2 modules that need persistence must access persistence through repository/store modules. Resume, Loop, Scheduler, Issue Reporter, Approval, and runtime business modules must not directly open, read, write, or delete checkpoint files.

Package 90 owns:

- approval request contract shape
- approval id, operator session id, package id, requested action, request reason, status, and metadata
- pending, approved, rejected, and expired approval statuses
- pure dict helpers for creating, approving, rejecting, and validating approval payloads

Package 90 must not:

- implement operator loop behavior
- call scheduler
- call task_runner
- call resume
- call replay
- write checkpoints
- mutate checkpoints
- own checkpoints
- own resume behavior
- own runtime state
- own operator state machine behavior
- own event ledger behavior
- own audit reader behavior
- persist approvals
- append events
- implement approval UI
- implement retry logic
- implement timers
- implement a transition engine
- change checkpoint persistence
- change checkpoint schema
- parse checkpoint files
- scan checkpoint directories
- discover checkpoints from event payloads
- treat Event Log as a Checkpoint Store index
- scan Event Ledger
- import Event Log
- delete events
- update events
- append events
- classify event severity
- perform issue analysis
- implement approval workflow
- decide operator actions
- filter business events
- trigger scheduler behavior
- trigger runtime behavior
- sort events during load
- infer missing sequence numbers
- reconstruct history
- repair history
- interpret history
- infer missing expected events
- validate lifecycle progression
- require approval events
- require checkpoint events
- require resume events
- require issue report events
- decide what should have existed
- duplicate lifecycle definitions
- duplicate transition rules
- duplicate repository responsibilities
- implement approval
- implement issue reporter
- introduce SQLite, Redis, memory caches, or multi-backend abstractions
- change broad runtime behavior
- change RC1 behavior

## Non-mainline Issues Found

- None for Package 90.

## Future Foundation Work

- Shared cross-module identity validation is deferred until Lifecycle, State Machine, Context, and Checkpoint have stabilized.
- Future modules must compose the foundation modules instead of reimplementing lifecycle phases, transition rules, context data, or checkpoint serialization.
- Future long-running state retention belongs to the Operator Loop, not Resume.
- Issue Reporter decides when to emit issue events.
- Future Approval integration decides when to emit approval events and how approval decisions are consumed.
- Resume may emit resume events in a future package, but Package 86 does not integrate Resume and Event Log.
- Operator Loop decides when events are emitted during execution.
- Future Audit Reader extensions must continue composing published repository read APIs instead of deriving persistence state from Event Ledger payloads.
