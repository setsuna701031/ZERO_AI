# Runtime Operator Console Review

Package 2701-2780 adds the first operator interface for the closed autonomous runtime loop.

This interface is CLI only. It introduces `zero-console submit`, `zero-console status`, and `zero-console run` commands through `cli/zero_operator_console.py`. No web UI is included; a web UI is the next optional layer.

`RuntimeOperatorService` remains the owner. The console loads package JSON, validates the package shape, and routes execution through `RuntimeOperatorService`. It does not create a new runtime execution pipeline and does not bypass intake, approval, gate, invocation, dispatch, session, result, closure, executor, mutation, validation, or rollback/commit status.

There is no authority bypass and no direct mutation. Dry-run mode keeps `mutation_allowed=False`. Controlled mode can enable the controlled real executor boundary, but mutation remains blocked unless a governed mutation adapter is supplied by the runtime owner.

Non-mainline issues are reported in the console payload through `non_mainline_issues`; invalid packages and unavailable latest status are deterministic reported states.
