# Runtime Executor Invocation Approval Review

Package 2273-2304 adds a record-only invocation approval layer after executor invocation preparation.

The layer approves prepared invocation metadata for later executor ownership without calling an executor. It consumes `ExecutorInvocationPreparationRecord`, preserves the runtime lineage through `executor_invocation_preparation_id`, and keeps `executor_invoked`, `execution_started`, and `runtime_mutated` false.

Ownership boundary:

- Invocation preparation describes the proposed call shape.
- Invocation approval records whether that prepared metadata is approved.
- Executor invocation remains downstream and separate.

This package intentionally does not import execution surfaces, mutate files, advance cursors, write progress, dispatch scheduling work, or invoke an executor.
