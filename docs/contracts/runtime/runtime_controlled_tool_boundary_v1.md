# Runtime Controlled Tool Boundary Contract v1

Status: disabled / tool admission boundary record only.

Schema: `zero.runtime.controlled_tool_boundary.v1`.

This contract reserves the controlled tool runtime boundary after executor binding. Executor binding alone grants
zero tool access. Tool admission requires a valid runtime session id, an active execution lease id, an active
capability grant id, an active executor binding id, and explicit tool authorization input.

Supported requested tool types:

- read_tool
- write_tool
- command_tool
- network_tool
- mutation_tool
- recovery_tool

Supported tool boundary statuses:

- denied
- admitted
- expired
- revoked

The deterministic tool boundary record includes tool boundary id, runtime session id, execution lease id,
capability grant id, executor binding id, requested tool name, requested tool type, tool boundary status,
admission flag, denial reason, and audit projection.

All default requests are denied. Admitted records are admission records only and never invoke a real tool,
launch subprocesses, run shell commands, read files, write files, use the network, mutate state, execute tasks,
start autonomy, self-start, or start a background loop.

Final decision: runtime owns identity, lease, capability, executor ownership, and a tool admission boundary;
runtime still performs zero real actions.
