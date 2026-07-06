# Runtime Executor Invocation Gate Review

Package 2305-2336 adds a record-only invocation gate layer after executor invocation approval.

The layer opens the metadata path for a future executor invocation without invoking an executor. It consumes `ExecutorInvocationApprovalRecord`, preserves the runtime lineage through `executor_invocation_approval_id`, and keeps `executor_invoked`, `execution_started`, and `runtime_mutated` false.

Ownership boundary:

- Invocation approval records whether prepared invocation metadata is approved.
- Invocation gate records that the approved metadata path is open.
- Executor invocation remains downstream and separate.

This package intentionally does not import execution surfaces, mutate files, advance cursors, write progress, dispatch scheduling work, or invoke an executor or adapter.
