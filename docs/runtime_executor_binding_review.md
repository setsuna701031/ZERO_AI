# Runtime Executor Binding Review

Status: disabled / executor binding record only.

Packages 1233-1240 introduce controlled executor attachment after capability authorization.

Review requirements:

- default runtime has no executor
- lease alone cannot bind executor
- capability alone cannot bind executor
- invalid capability cannot bind executor
- unauthorized request creates no binding
- authorized request creates a deterministic binding record
- binding does not execute anything
- revoked binding blocks executor
- expired binding blocks executor
- executor cannot bypass the session, lease, and capability chain

Final review decision: GO for executor ownership record only; NO-GO for execution.
