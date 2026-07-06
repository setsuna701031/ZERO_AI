# Runtime Governed Mutation Adapter Attachment Seal

The governed mutation adapter attachment is sealed as the bridge from the controlled runtime loop to the existing governed mutation tooling.

No new mutation system is introduced. The adapter translates controlled mutation requests and delegates to the existing governed mutation runtime, repo sandbox, validation, and rollback components.

No direct file writes are introduced in the adapter or console. RuntimeOperatorService remains the owner, and the console remains a CLI-only facade.

Rollback remains mandatory and validation remains required. Validation failure must roll back; commit is allowed only after validation passes.

Expected final status: `operator_console_available=True`, `runtime_loop_closed=True`, `real_executor_enabled=True`, `controlled_mutation_available=True`, `governed_mutation_adapter_attached=True`, `validation_required=True`, `rollback_available=True`, and `web_ui_available=False`.
