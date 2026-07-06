# Runtime Operator Console Seal

The runtime operator console is sealed as the first operator interface for the autonomous runtime loop.

The console is CLI only. It exposes submit, status, and run commands for operator use and does not include a web UI. `web_ui_available=False` is the expected status for this bundle.

`RuntimeOperatorService` remains the owner. The console routes through the service and does not bypass authority, approval, executor, controlled mutation, validation, rollback, or commit boundaries.

The console performs no direct mutation. It does not provide an executor file-mutation shortcut and does not replace the governed repo edit sandbox and rollback pipeline.

Expected final status: `operator_console_available=True`, `runtime_loop_closed=True`, `controlled_mutation_available=True`, and `web_ui_available=False`.
