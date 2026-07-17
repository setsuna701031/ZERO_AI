# Runtime Autonomous Persistence Survival Seal

## Seal

Runtime Autonomous Persistence and Survival v1 is sealed for Package 1673-1696.

## Guarantees

- runtime session identity is persisted
- active cursor is persisted
- current tick index is persisted
- last completed work id is persisted
- lease id and lease expiry are persisted
- paused and stopped state are persisted
- resume requires a valid checkpoint
- missing checkpoints are denied
- expired leases require renewal authority
- renewal requires active runtime state and no emergency stop

## Non-Effects

- no work is performed
- no progress state is mutated
- no cursor is advanced
- no unbounded loop is started

Final decision: GO for Runtime Autonomous Persistence and Survival only.
