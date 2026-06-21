# Runtime Ownership Closure

Schema: `zero.runtime_ownership_closure.v1`

## Purpose

Runtime ownership closure seals the owner graph that sits above the already
sealed authority, capability, identity, evidence, and persistence graph.
Ownership is not permission, identity, evidence, or persistence.  It records the
canonical owner responsible for each runtime layer and rejects owner drift across
runtime, resume, continuation, and replan handoffs.

## Canonical owner graph

The closure uses one explicit graph:

- `goal_owner`
- `session_owner`
- `execution_owner`
- `capability_owner`
- `evidence_owner`
- `persistence_owner`

Every runtime layer may carry this graph, but no layer may replace it.  Resume,
continuation, and replan records may preserve the same graph only; they may not
reassign ownership to themselves.

## Required invariants

1. Goal ownership has one canonical source.
2. Session ownership has one canonical source.
3. Execution ownership has one canonical source.
4. Capability ownership has one canonical source.
5. Evidence ownership has one canonical source.
6. Persistence ownership has one canonical source.
7. Resume must preserve the original owner graph.
8. Continuation must preserve the original owner graph while only adding branch semantics elsewhere.
9. Replan must preserve the original owner graph while only adding branch semantics elsewhere.
10. Identity binding must remain attached to the same owner graph.
11. Owner fingerprints must not drift between records.
12. Fallback owners such as `unknown`, `default`, `legacy`, `runtime`, `system`, or `fallback` are rejected.

## Non-mainline findings

- Existing `core/runtime/runtime_ownership.py` still contains an older
  owner/resource/action permission matrix.  It is currently a policy/authority
  compatibility surface, not the canonical closure graph.  Future work should
  either explicitly bridge it into this closure or retire the parallel naming to
  avoid ownership/authority mixing.
- `aer_runtime_ownership_bridge.py` still records a transition-oriented
  ownership artifact for the thin runtime bridge.  This is useful evidence, but
  it is not a canonical owner source.
- Several older runtime ownership scan/policy modules are audit tools rather
  than closure authorities.  They should remain evidence producers and must not
  silently become owner sources.

## Validation

Primary test:

```powershell
pytest -q tests/test_runtime_ownership_closure.py
```

Regression set:

```powershell
pytest -q tests/test_runtime_persistence_closure.py tests/test_runtime_evidence_closure.py tests/test_runtime_identity_closure.py tests/test_runtime_capability_propagation_closure.py tests/test_runtime_authority_source_closure.py tests/test_runtime_execution_capability_unification_audit.py
python -m compileall core/runtime core/evidence core/goals core/tasks core/session core/adaptive tests
git diff --check
```
