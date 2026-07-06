# Runtime Capability Grant Review

Status: disabled / capability grant record only.

Packages 1225-1232 introduce a capability authorization layer between runtime execution leases and executor
attachment.

Review requirements:

- session default has no capability
- lease default has no capability
- invalid lease cannot grant capability
- unauthorized request creates no grant
- authorized request creates a deterministic grant record
- all capabilities default false
- grant can expire
- grant can revoke
- revoked and expired grants cannot authorize executor
- capability grant does not execute anything

Final review decision: GO for permission model only; NO-GO for executor attachment.
