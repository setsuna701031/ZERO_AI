# Runtime Read-Only Tool Adapter Audit

Status: disabled / read adapter registration and dry-run read planning only.

Audit decision:

`reserved_runtime_read_only_tool_adapter_plan_record_only`

The audit record must include:

- read adapter request validation
- deterministic read adapter record when authorized
- runtime session id
- execution lease id
- capability grant id
- executor binding id
- tool boundary id
- tool invocation id
- requested resource
- read status
- synthetic read result
- denial reason
- resource ownership check
- read scope model
- expiration and revocation evidence
- proof that no file open, pathlib read, filesystem access, write, mutation, subprocess, shell, network, task execution, autonomy, or background loop occurred

Final audit decision: reserved runtime read-only tool adapter plan record only.
