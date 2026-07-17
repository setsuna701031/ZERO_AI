# Runtime Executor Binding Audit

Status: disabled / executor binding record only.

Audit decision:

`reserved_runtime_executor_binding_record_only`

The audit record must include:

- binding request validation
- binding record when authorized
- runtime session id
- execution lease id
- capability grant id
- executor id and executor type
- binding status
- expiration model
- revocation model
- heartbeat projection
- proof that no executor, task, tool, subprocess, mutation, IO, autonomy, self-start, or background loop occurred

Final audit decision: reserved runtime executor binding record only.
