# Runtime Queue Worker Pickup Seal

## Seal

Runtime Queue Worker Pickup v1 is sealed for Package 1825-1856.

## Guarantees

- valid admitted queue entries can be claimed
- missing queue entries are denied
- non-admitted queue entries are denied
- duplicate claims are denied
- invalid lineage is denied
- worker claim records preserve goal, work package, runtime session, and queue entry identity
- queue status moves from `queued` to `claimed`
- CLI `zero run "task"` exposes claimed pickup status

## Non-Effects

- no task execution
- no direct scheduler call
- no direct executor call
- no progress memory mutation
- no cursor mutation

Final decision: GO for Runtime Queue Worker Pickup only.
