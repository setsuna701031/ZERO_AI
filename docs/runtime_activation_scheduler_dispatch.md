# Runtime Activation Scheduler Dispatch Boundary

This package defines the boundary between scheduler planning and future task dispatch.

## Scope

This is preview-only. It snapshots scheduler planning metadata, prepares deterministic future dispatch metadata, preserves identity and lineage metadata, and keeps dispatch and execution disabled.

This package must not dispatch or execute tasks.

## Disabled Boundaries

- Scheduler runtime calls are forbidden.
- Executor imports and calls are forbidden.
- Queue reads are forbidden.
- Queue writes are forbidden.
- Filesystem IO is forbidden.
- Database IO is forbidden.
- Subprocess use is forbidden.
- Tool execution is forbidden.
- Background workers are forbidden.
- Runtime mutation is forbidden.

## Dispatch Metadata

The preview includes:
- scheduler_dispatch_ready
- dispatch_created
- dispatch_allowed
- execution_allowed
- executor_admission_allowed
- runtime_mutation_allowed
- dispatch_status
- dispatch_reason
- identity_snapshot
- lineage_snapshot
- scheduler_planning_snapshot
- dispatch_preview

scheduler_dispatch_ready may be True. dispatch_created must always be False. dispatch_allowed must always be False. execution_allowed must always be False. executor_admission_allowed must always be False. runtime_mutation_allowed must always be False.

## Final Decision

GO only for disabled scheduler dispatch preview. Dispatch creation, dispatch, executor admission, execution, queue reads, queue writes, filesystem IO, database IO, tools, background workers, and runtime mutation remain disabled.
