# Runtime Governed Mutation Adapter Attachment Review

Package 2781-2860 attaches the existing governed mutation runtime to the controlled mutation adapter boundary used by `RuntimeOperatorService` and `zero_operator_console --controlled`.

This does not create a new mutation system. `RuntimeGovernedMutationAdapter` translates `RuntimeControlledMutationRequest` into the existing `MutationGatewayRequest` shape and calls the existing governed mutation runtime, repo sandbox, validation, and rollback boundary.

The adapter does not perform direct file writes and does not create a new file writer. The executor still cannot mutate files directly; it can only produce requested changes that are later routed through `RuntimeOperatorService` and the governed mutation adapter.

Rollback remains mandatory. Validation failure is reported as rollback-required and rollback-completed when the governed runtime rolls back. Commit is allowed only when validation passes.

The operator console remains CLI-only and a thin facade. `--dry-run` attaches no mutation adapter. `--controlled` attaches the governed adapter when available and otherwise preserves the deterministic blocked status.
