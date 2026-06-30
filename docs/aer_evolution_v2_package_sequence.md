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
8. Package 85 - Stop Condition
9. Package 86 - Human Approval Boundary
10. Package 87 - Issue Reporter
11. Package 88 - Long-running Operator Loop
12. Package 89+ - Scheduler / Runtime integration

## Package Boundaries

Packages 78 through 88 define v2 foundation surfaces without changing RC1 scheduler, task runner, or operator runtime behavior.

Scheduler and runtime integration begins only at Package 89 or later.

## Current Package

Package 83 adds the checkpoint repository/store boundary for v2 checkpoint persistence.

All future v2 modules that need persistence must access persistence through repository/store modules. Resume, Loop, Scheduler, Issue Reporter, Approval, and runtime business modules must not directly open, read, write, or delete checkpoint files.

Package 83 must not:

- implement resume
- implement operator loop behavior
- call scheduler
- call task_runner
- introduce SQLite, Redis, memory caches, or multi-backend abstractions
- change broad runtime behavior
- change RC1 behavior

## Non-mainline Issues Found

None in this package sequence cleanup.

## Future Foundation Work

- Shared cross-module identity validation is deferred until Lifecycle, State Machine, Context, and Checkpoint have stabilized.
- Future modules must compose the foundation modules instead of reimplementing lifecycle phases, transition rules, context data, or checkpoint serialization.
