# Runtime Persistence Closure

Runtime Persistence Closure seals the handoff from a live runtime execution graph
into persistence, snapshots, resume, and recovered runtime state.

## Canonical flow

```text
Authority Decision
  -> Capability
  -> Identity Graph
  -> Evidence
  -> Persistence
  -> Snapshot
  -> Resume
  -> Recovered Graph
```

Persistence is not allowed to mint, replace, or upgrade identity.  It may only
serialize an execution graph that has already been issued by the runtime
identity / authority / capability path.

## Required invariants

1. Persistence serializes the same execution graph that the live runtime uses.
2. Snapshots preserve the same execution fingerprint.
3. Resume validates the original execution fingerprint instead of reminting.
4. Recovered state keeps the same authority decision, capability, identity, and evidence refs.
5. Evidence refs cannot be replaced between persistence and resume.
6. Fallback identities such as `unknown`, `default`, `legacy`, `runtime`, and `system` are rejected.
7. Hidden recovery paths cannot override lineage, session, execution, authority, or capability IDs.

## Non-mainline findings

Mandatory findings to keep visible for the next audit layer:

- Existing legacy persistence and snapshot paths must remain inventory targets.
- Any recovery path that accepts partial serialized identity must be treated as unsafe until it validates the canonical execution fingerprint.
- Evidence persistence drift is a high-risk non-mainline issue because a green runtime can still become non-auditable after restart.
- Line-ending warnings observed during validation are not semantic failures, but should remain visible in release notes until normalized.

No finding should be omitted just because the closure tests pass.
