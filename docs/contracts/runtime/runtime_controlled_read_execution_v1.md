# Runtime Controlled Read Execution Contract v1

Status: controlled read execution only.

Schema: `zero.runtime.controlled_read_execution.v1`.

This contract introduces the first real read execution bridge. Reads are allowed only through an approved read
adapter. The runtime chain must include active, non-expired, non-revoked runtime session, execution lease,
capability grant, executor binding, tool boundary, tool invocation, and read adapter records.

The read execution record includes read execution id, read adapter id, requested resource, execution status,
content digest, content metadata, failure reason, and audit projection.

Rules:

- read operation goes through the adapter only
- direct filesystem bypass is forbidden
- scope validation is required
- resource ownership is required
- result is an immutable evidence record
- replay evidence stores digest and metadata, not file content

Allowed operation: controlled file read through the approved adapter only.

Forbidden operations: file write, append, delete, rename, chmod, mutation, subprocess, shell, network, task
execution, autonomy, self-start, and background loop.

Final decision: runtime can observe approved resources, but cannot modify anything.
