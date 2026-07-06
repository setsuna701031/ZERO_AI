# Runtime Execution Lease Contract v1

Status: disabled / controlled execution lease record only.

Schema: `zero.runtime.execution_lease.v1`.

This contract reserves controlled execution lease attachment after runtime session birth. Runtime sessions
remain inert by default, and no lease is created automatically. Lease creation requires a valid
`runtime_session_id`, explicit authorization input, and an active inert session state.

The lease is a deterministic record only. It includes:

- lease_id
- lease ownership
- lease status: inactive, granted, expired, revoked
- expiration model
- revocation model
- heartbeat projection
- audit evidence

The lease never starts an executor, executes tasks, launches subprocesses, mutates files, performs IO, calls
tools, starts autonomy, self-starts, or starts a background loop.

Final decision: runtime has identity plus controlled lease record, but zero execution capability.
