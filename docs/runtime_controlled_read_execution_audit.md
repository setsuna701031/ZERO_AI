# Runtime Controlled Read Execution Audit

Status: controlled read execution only.

Audit decision:

`reserved_runtime_controlled_read_execution_only`

The audit record must include:

- read execution request validation
- read execution record
- read adapter id
- requested resource
- execution status
- content digest
- content metadata
- failure reason and failure ownership
- audit projection
- read replay record
- proof that no write, append, delete, rename, chmod, mutation, subprocess, shell, network, task execution, autonomy, self-start, or background loop occurred

Final audit decision: reserved runtime controlled read execution only.
