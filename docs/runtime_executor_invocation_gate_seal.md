# Runtime Executor Invocation Gate Seal

Final decision: GO for Runtime Executor Invocation Gate only.

Sealed guarantees:

- Invocation gate consumes only invocation approval metadata.
- Valid approval opens gate metadata.
- Rejected approval creates rejected gate metadata.
- Duplicate gate creation is denied.
- `executor_invoked` is always false.
- `execution_started` is always false.
- `runtime_mutated` is always false.

Downstream ownership remains separate:

- Executor invocation owns any actual executor call.
- Executor execution owns execution start.
- Result intake owns returned evidence.
