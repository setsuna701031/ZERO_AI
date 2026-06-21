# Runtime Evidence Closure Audit

Runtime evidence is now treated as a passive closure layer over the canonical runtime identity graph.
Evidence may record, seal, fingerprint, persist, and resume identity; it may not mint or repair identity.

## Closed chain

```text
Runtime Identity Graph
  -> Runtime Evidence Record
  -> Runtime Evidence Registry
  -> Persistence Evidence
  -> Resume Evidence
```

Every evidence payload must preserve the same:

```text
goal_id
root_goal_id
source_goal_id
goal_lineage_id
branch_id
branch_type
session_id
runtime_session_id
execution_id
capability_id
evidence_id
```

## Rules

1. Evidence must be sealed against an existing canonical identity graph.
2. Evidence must not generate goal, session, runtime session, execution, or capability identity.
3. Evidence may only add `evidence_id`, `identity_graph`, `identity_fingerprint`, and an evidence fingerprint.
4. Persistence and resume records must match the same identity fingerprint.
5. Evidence IDs must not be reissued inside the same runtime evidence chain.
6. Forbidden fallback identities are rejected: `unknown`, `default`, `legacy`, `runtime`, `system`, `none`, `null`, and `undefined`.

## Non-mainline findings

- Legacy evidence catalog/registry paths remain metadata-oriented and may still accept records that do not carry a full runtime identity graph. This is documented as compatibility surface, not as a runtime evidence authority.
- Some older evidence records contain only `goal_id` and `metadata`; they are not promoted to runtime evidence closure records unless the canonical identity graph is supplied.
- Runtime evidence closure is intentionally passive. Any future path that needs to write runtime evidence should call the closure validator instead of manufacturing fallback identity values locally.
