# Runtime Activation Queue Visibility Gate

This package defines the visibility boundary between queue state and scheduler discovery.

## Scope

This is preview-only. It snapshots queue state metadata, prepares future scheduler visibility metadata, and keeps task visibility disabled.

This package must not expose tasks to scheduler.

## Disabled Boundaries

- Scheduler imports and calls are forbidden.
- Executor imports and calls are forbidden.
- Queue reads are forbidden.
- Queue writes are forbidden.
- Filesystem IO is forbidden.
- Database IO is forbidden.
- Subprocess use is forbidden.
- Tool execution is forbidden.
- Background workers are forbidden.
- Runtime mutation is forbidden.

## Visibility Metadata

The preview includes:
- visibility_gate_ready
- queue_visible
- scheduler_visibility_allowed
- task_discovery_allowed
- runtime_mutation_allowed
- visibility_status
- visibility_reason
- identity_snapshot
- lineage_snapshot
- queue_state_snapshot

visibility_gate_ready may be True. queue_visible must always be False. scheduler_visibility_allowed must always be False. task_discovery_allowed must always be False. runtime_mutation_allowed must always be False.

## Final Decision

GO only for disabled queue visibility gate preview. Queue visibility, scheduler discovery, queue reads, queue writes, filesystem IO, database IO, execution, tools, background workers, and runtime mutation remain disabled.
