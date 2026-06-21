# Runtime Governance Graph Closure

Runtime Governance Graph Closure binds the previously sealed runtime layers into
one canonical graph.

## Canonical flow

```text
Authority
  -> Capability
  -> Identity
  -> Ownership
  -> Mutation
  -> Evidence
  -> Persistence
  -> Resume
```

The closure is passive. It does not grant authority, issue capability, assign
ownership, mutate state, write evidence, or persist data. It only validates that
all records refer to the same already-sealed governance graph.

## Required invariants

1. Authority and capability refer to the same authority decision and capability ID.
2. Capability and identity refer to the same execution and identity fingerprint.
3. Identity and ownership refer to the same owner graph and ownership fingerprint.
4. Ownership and mutation refer to the same mutation graph.
5. Mutation and evidence refer to the same evidence ID.
6. Evidence and persistence refer to the same persistence ID.
7. Persistence and resume refer to the same governance fingerprint.
8. Continuation cannot replace source lineage or mint a second governance graph.
9. Replan cannot replace lineage or mint a second governance graph.
10. Hidden direct, bypass, legacy, or parallel governance paths are rejected.

## Non-mainline findings

Mandatory findings to keep visible for follow-up audit work:

- Legacy records that contain only partial governance fields remain unsafe until
  they are sealed against the canonical graph.
- Any layer that accepts `unknown`, `default`, `legacy`, `runtime`, `system`,
  `fallback`, `wildcard`, or `unsealed` governance values can silently split the
  graph and must remain an inventory target.
- Continuation and replan paths are high-risk because they can create a second
  lineage graph even when the individual closure tests stay green.
- Resume paths are high-risk because persisted data can pass syntax checks while
  pointing to a different governance fingerprint.
- Line-ending warnings observed during validation are not semantic failures, but
  should remain visible in release notes until normalized.

No finding should be omitted just because tests pass.
