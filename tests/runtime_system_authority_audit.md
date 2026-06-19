# Runtime SYSTEM Authority Audit

## Scope

This audit is read-only. It maps the remaining `SYSTEM` authority surface after the recently committed runtime identity, status, and mutation-sovereignty proof packages.

Recent authority chain:

- `Seal runtime task payload and status write authority`
- `Seal cross-runtime identity propagation`
- `Seal runtime identity authority v2`
- `Seal resume runtime status authority`
- `Add runtime mutation sovereignty proofs`

## Finding summary

`SYSTEM` authority is still a wildcard in `core/runtime/runtime_ownership.py`:

```python
if runtime_owner is RuntimeOwner.SYSTEM:
    return True
```

That means `RuntimeOwner.SYSTEM` can currently pass every resource/action pair accepted by `can_access(...)`, regardless of whether a live issuer token, scoped capability, or explicit break-glass reason exists.

This audit does not change production code. It pins the current state so the next package can seal it without confusing the mutation-gateway proof with a separate SYSTEM-authority migration.

## Authority map

| Surface | Current state | Risk |
| --- | --- | --- |
| `core/runtime/runtime_ownership.py` | Defines `RuntimeOwner.SYSTEM` and grants wildcard `True` in `can_access` | High: policy bypass surface |
| `core/runtime/runtime_mutation_guard.py` | Delegates to `can_access`; therefore inherits SYSTEM wildcard | High: mutation guard can be bypassed by SYSTEM owner |
| `core/runtime/runtime_authority_seal.py` | Uses private object issuer tokens for live runtime execution/completion/evidence authorities | Lower: token-based, not SYSTEM-string based |
| `core/runtime/runtime_execution_authority_gate.py` / `core/runtime/runtime_execution_authority_policy.py` | Execution authority domain; should not become a SYSTEM fallback | Watch |
| `core/runtime/runtime_evidence_authority.py` | Evidence authority domain; should remain token/facade based | Watch |
| `core/runtime/runtime_file_service.py` | Uses `identity_type: SYSTEM` for system identity metadata | Medium: metadata identity, not necessarily policy authority |
| `core/runtime/execution_gateway.py` | Uses `identity_type: SYSTEM` for subprocess gateway metadata | Medium: metadata identity, not necessarily ownership authority |

## Proof classification

The accompanying tests prove:

1. `RuntimeOwner.SYSTEM` exists.
2. `can_access(RuntimeOwner.SYSTEM, every RuntimeResource, every RuntimeAction)` currently returns `True`.
3. `RuntimeMutationGuard` delegates to `can_access`, so it inherits the SYSTEM wildcard.
4. `runtime_authority_seal.py` uses private object issuer tokens and does not rely on a textual SYSTEM issuer.
5. SYSTEM metadata identities exist in runtime gateway/file-service surfaces and must be classified separately from policy authority.

## Recommended next seal

Next package: **Seal Runtime SYSTEM Authority Boundary**.

Dependency order:

1. Introduce a narrow break-glass capability or issuer token for SYSTEM-level actions.
2. Remove unconditional `RuntimeOwner.SYSTEM -> True` from `can_access`.
3. Require explicit rule entries or a scoped break-glass token for SYSTEM writes/transitions/dispatches.
4. Keep read-only monitor-style inspection separate from mutation authority.
5. Add enforcement tests proving SYSTEM cannot write every runtime resource by default.
6. Leave metadata identities such as `identity_type: SYSTEM` intact unless they are used as policy authority.

## Non-mainline issues

No production defect was modified in this audit. The remaining issue is architectural: SYSTEM is a policy wildcard, while some files also use SYSTEM as metadata identity. The seal should separate these meanings instead of deleting all SYSTEM metadata strings.
