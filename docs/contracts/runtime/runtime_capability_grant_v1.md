# Runtime Capability Grant Contract v1

Status: disabled / capability grant record only.

Schema: `zero.runtime.capability_grant.v1`.

This contract reserves the capability authorization layer between execution lease and executor. A lease alone
grants zero capability. A capability grant requires a valid runtime session id, an active execution lease id,
and explicit authorization input.

Supported capability states:

- none
- granted
- revoked
- expired

Initial capability categories:

- read_access
- write_access
- tool_access
- execution_access
- mutation_access
- network_access

All capability categories default to false. Capability grant records are deterministic and include grant id,
owner session id, owner lease id, granted capabilities, denied capabilities, grant status, expiration model,
revocation model, and audit projection.

The grant never starts an executor, executes tasks, launches subprocesses, mutates files, performs IO, calls
tools, starts autonomy, self-starts, or starts a background loop.

Final decision: runtime owns identity, lease, and permission model; executor remains detached.
