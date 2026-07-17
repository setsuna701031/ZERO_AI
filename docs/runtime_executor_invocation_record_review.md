# Runtime Executor Invocation Record Review

Package 2337-2368 adds a record-only invocation event layer after executor invocation gate opening.

The layer records that an executor invocation event is ready to be emitted without invoking an executor. It consumes `ExecutorInvocationGateRecord`, preserves the runtime lineage through `executor_invocation_gate_id`, freezes invocation metadata, and keeps `executor_invoked`, `execution_started`, and `runtime_mutated` false.

Ownership boundary:

- Invocation gate records that the approved metadata path is open.
- Invocation record freezes the event metadata for a future invocation event.
- Executor invocation remains downstream and separate.

This package intentionally does not import execution surfaces, mutate files, advance cursors, write progress, dispatch scheduling work, or invoke an executor or adapter.
