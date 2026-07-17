# Runtime Activation Queue Persistence Preview

This package adds a preview-only persistence boundary after the queue commit gate.

## Scope

This is preview-only. It snapshots identity and lineage metadata, produces deterministic persistence preview metadata, and indicates future queue persistence target metadata only.

This package must not write to queue or mutate runtime state. Future queue persistence remains unimplemented.

## Disabled Boundaries

- Queue writes are forbidden.
- File IO is forbidden.
- Queue implementation imports are forbidden.
- Scheduler imports and calls are forbidden.
- Executor imports and calls are forbidden.
- Subprocess use is forbidden.
- Tool execution is forbidden.
- Background workers are forbidden.
- Runtime mutation is forbidden.
- Repo mutation is forbidden.

## Persistence Metadata

The preview includes:
- persistence_preview_ready
- queue_persistence_allowed
- queue_write_allowed
- runtime_mutation_allowed
- persistence_status
- persistence_reason
- identity_snapshot
- lineage_snapshot

persistence_preview_ready may be True. queue_persistence_allowed must always be False. queue_write_allowed must always be False. runtime_mutation_allowed must always be False.

## Final Decision

GO only for disabled queue persistence preview. Queue persistence, queue writes, scheduling, execution, tools, runtime mutation, and repo/file mutation remain disabled.
