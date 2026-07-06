# Runtime Execution Session Start Dry-Run Review

Package 2401-2432 adds the first execution session lifecycle boundary after executor invocation dispatch binding.

This is execution lifecycle start only. It consumes `ExecutorInvocationDispatchResult` and creates a deterministic `RuntimeExecutionSessionStartResult` with `execution_started=True` only when `dry_run=True`. Mutation remains disabled through `mutation_allowed=False`, and the real executor remains disabled.

Sealed behavior:

- Missing dispatch results are rejected.
- Dispatch results with `executor_invoked=False` are rejected.
- Dispatch results that already started execution are rejected.
- `dry_run=False` is rejected.
- `mutation_allowed=True` is rejected.
- Duplicate session start for the same `dispatch_id` is rejected.
- Lineage mismatch is rejected.

The next package is Runtime Execution Result Capture Dry-Run Boundary.
