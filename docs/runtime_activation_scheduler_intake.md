# Runtime Activation Scheduler Intake Boundary

This package defines the boundary where scheduler will eventually receive visible queue tasks.

## Scope

This is preview-only. It snapshots the queue visibility decision, prepares future scheduler intake metadata, preserves identity and lineage metadata, and keeps scheduler intake disabled.

This package must not schedule or execute tasks.

## Disabled Boundaries

- Scheduler imports are forbidden.
- Scheduler calls are forbidden.
- Executor imports and calls are forbidden.
- Queue reads are forbidden.
- Queue writes are forbidden.
- Filesystem IO is forbidden.
- Database IO is forbidden.
- Subprocess use is forbidden.
- Tool execution is forbidden.
- Background workers are forbidden.
- Runtime mutation is forbidden.

## Scheduler Intake Metadata

The preview includes:
- scheduler_intake_ready
- scheduler_available
- scheduler_task_received
- scheduling_allowed
- execution_allowed
- runtime_mutation_allowed
- scheduler_status
- scheduler_reason
- identity_snapshot
- lineage_snapshot
- visibility_snapshot

scheduler_intake_ready may be True. scheduler_available must always be False. scheduler_task_received must always be False. scheduling_allowed must always be False. execution_allowed must always be False. runtime_mutation_allowed must always be False.

## Final Decision

GO only for disabled scheduler intake preview. Scheduler intake, scheduler task receipt, scheduling, execution, queue reads, queue writes, filesystem IO, database IO, tools, background workers, and runtime mutation remain disabled.
