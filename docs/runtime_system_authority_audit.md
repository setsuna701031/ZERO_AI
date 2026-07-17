# Runtime SYSTEM Authority Audit

## Scope

This audit originally mapped the remaining `SYSTEM` authority surface after the runtime identity, status, and mutation-sovereignty proof packages. It is now updated to reflect the enforcement seal.

Recent authority chain:

- `Seal runtime task payload and status write authority`
- `Seal cross-runtime identity propagation`
- `Seal runtime identity authority v2`
- `Seal resume runtime status authority`
- `Add runtime mutation sovereignty proofs`
- `Add runtime system authority audit`

## Finding summary

`SYSTEM` authority is no longer a wildcard in `core/runtime/runtime_ownership.py`.

The previous implementation granted all declared resource/action pairs through:

```python
if runtime_owner is RuntimeOwner.SYSTEM:
    return True
```

The current sealed implementation keeps `RuntimeOwner.SYSTEM` as a metadata/bootstrap owner but routes policy decisions through explicit `_SYSTEM_ALLOWED_RULES` and `system_authority_rules()`.

## Authority map

| Surface | Current state | Risk |
| --- | --- | --- |
| `core/runtime/runtime_ownership.py` | Defines scoped SYSTEM authority rules | Sealed for default ownership policy |
| `core/runtime/runtime_mutation_guard.py` | Delegates to `can_access`; inherits scoped SYSTEM behavior | Sealed at mutation guard boundary |
| `core/runtime/runtime_authority_seal.py` | Uses private object issuer tokens for live runtime execution/completion/evidence authorities | Sealed token path |
| `core/runtime/runtime_execution_authority_gate.py` / `core/runtime/runtime_execution_authority_policy.py` | Execution authority domain; should not add SYSTEM fallback | Watch |
| `core/runtime/runtime_evidence_authority.py` | Evidence authority domain; should remain token/facade based | Watch |
| `core/runtime/runtime_file_service.py` | Uses `identity_type: SYSTEM` for system identity metadata | Metadata only |
| `core/runtime/execution_gateway.py` | Uses `identity_type: SYSTEM` for subprocess gateway metadata | Metadata only |

## Enforcement classification

The accompanying tests now prove:

1. `RuntimeOwner.SYSTEM` exists but is explicitly scoped.
2. `can_access(RuntimeOwner.SYSTEM, every RuntimeResource, every RuntimeAction)` no longer returns all `True`.
3. `RuntimeMutationGuard` delegates to `can_access`, so it rejects SYSTEM mutations outside `_SYSTEM_ALLOWED_RULES`.
4. `runtime_authority_seal.py` uses private object issuer tokens and does not rely on a textual SYSTEM issuer.
5. SYSTEM metadata identities exist in runtime gateway/file-service surfaces and are classified separately from policy authority.

## Non-mainline issues

The historical audit file lives under `tests/` because that was the committed location of the audit package. Canonical documentation for the enforcement seal is now in `docs/runtime_system_authority_enforcement.md`.
