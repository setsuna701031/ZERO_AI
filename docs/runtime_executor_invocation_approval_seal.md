# Runtime Executor Invocation Approval Seal

Final decision: GO for Invocation Approval only.

Sealed guarantees:

- Invocation approval consumes only prepared invocation metadata.
- Valid preparation creates approved metadata.
- Rejected preparation creates rejected approval metadata.
- Duplicate approval is denied.
- Invalid lineage is denied.
- `executor_invoked` is always false.
- `execution_started` is always false.
- `runtime_mutated` is always false.

Downstream ownership remains separate:

- Executor invocation owns any actual executor call.
- Executor execution owns execution start.
- Result intake owns returned evidence.
