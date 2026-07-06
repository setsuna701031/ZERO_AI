# Runtime Read-Only Tool Adapter Contract v1

Status: disabled / read adapter registration and dry-run read planning only.

Schema: `zero.runtime.read_only_tool_adapter.v1`.

This contract introduces the first controlled real-world adapter boundary. It allows only read adapter
registration and dry-run read planning. No actual filesystem read is allowed.

Read adapter planning requires runtime session id, execution lease id, capability grant id, executor binding id,
tool boundary id, tool invocation id, and explicit read capability in the capability grant.

Supported read statuses:

- denied
- planned
- expired
- revoked

The deterministic read adapter record includes read adapter id, runtime session id, execution lease id,
capability grant id, executor binding id, tool boundary id, tool invocation id, requested resource, read status,
synthetic read result, denial reason, and audit projection.

Resource ownership and read scope are checked as data only. Read results remain synthetic and contain no file
content. The adapter never calls file open, pathlib read helpers, filesystem access, writes, mutations,
subprocesses, shells, network, task execution, autonomy, or background loops.

Final decision: runtime can create a governed read plan, but still cannot touch the filesystem.
