# Runtime Executor Binding Contract v1

Status: disabled / executor binding record only.

Schema: `zero.runtime.executor_binding.v1`.

This contract reserves controlled executor attachment after capability authorization. A runtime session, lease,
or capability grant alone cannot attach an executor. Binding requires a valid runtime session id, an active
execution lease id, an active capability grant id, and explicit bind authorization.

Supported binding states:

- detached
- bound
- revoked
- expired

Reserved executor types:

- task_executor
- tool_executor
- mutation_executor
- recovery_executor

The deterministic binding record includes executor binding id, runtime session id, execution lease id,
capability grant id, executor id, executor type, and binding status. All executors are disabled initially,
including bound records.

Binding records include expiration, revocation, heartbeat projection, and audit evidence. Binding never starts
an executor, executes tasks, launches subprocesses, mutates files, performs IO, calls tools, starts autonomy,
self-starts, or starts a background loop.

Final decision: runtime owns identity, lease, permission, and executor ownership; executor still cannot perform
actions.
