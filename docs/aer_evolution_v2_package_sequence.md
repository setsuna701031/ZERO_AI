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
11. Package 88 - Stop Condition
12. Package 89 - Human Approval Boundary
13. Package 90 - Issue Reporter
14. Package 91 - Long-running Operator Loop
15. Package 92+ - Scheduler / Runtime integration

## Package Boundaries

Packages 78 through 91 define v2 foundation surfaces without changing RC1 scheduler, task runner, or operator runtime behavior.

Scheduler and runtime integration begins only at Package 92 or later.

## Current Package

Package 87 adds the Audit Reader as a read-only composition layer over available v2 read repositories.

All future v2 modules that need persistence must access persistence through repository/store modules. Resume, Loop, Scheduler, Issue Reporter, Approval, and runtime business modules must not directly open, read, write, or delete checkpoint files.

Package 87 owns:

- loading a read-only operator timeline from available read repositories
- building a constrained audit summary
- building a read-only audit view
- validating audit view shape
- preserving event ledger physical append order

Package 87 must not:

- implement operator loop behavior
- call scheduler
- call task_runner
- call resume
- call replay
- write checkpoints
- mutate checkpoints
- discover checkpoints from event payloads
- treat Event Log as a Checkpoint Store index
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

- Checkpoint Store does not currently expose a read-only checkpoint enumeration or identity-scoped snapshot query API. Because Audit Reader must not derive checkpoint discovery from Event Ledger payloads or duplicate repository lookup rules, Package 87 audit views include event timeline entries only until a future package explicitly adds checkpoint enumeration to Checkpoint Store.

## Future Foundation Work

- Shared cross-module identity validation is deferred until Lifecycle, State Machine, Context, and Checkpoint have stabilized.
- Future modules must compose the foundation modules instead of reimplementing lifecycle phases, transition rules, context data, or checkpoint serialization.
- Future long-running state retention belongs to the Operator Loop, not Resume.
- Issue Reporter decides when to emit issue events.
- Approval decides when to emit approval events.
- Resume may emit resume events in a future package, but Package 86 does not integrate Resume and Event Log.
- Operator Loop decides when events are emitted during execution.
- Future checkpoint snapshot inclusion in Audit Reader requires an explicit Checkpoint Store read API, not event-ledger-derived checkpoint discovery.
