# Runtime Mutation Sovereignty Proof

Status: proof package only. Production code unchanged.

## Purpose

This proof package pins the current mutation authority state after the runtime identity and status authority seals. It proves that the canonical `RuntimeMutationGateway` exists and contains real identity, authority, capability, protection, and policy gates, while also proving that several legacy mutation surfaces still sit outside that gateway.

This document is intentionally not a seal. It is the dependency proof for the next seal: `Runtime Mutation Gateway Sovereignty Seal`.

## Files added

- `tests/test_runtime_mutation_gateway_sovereignty_seal.py`
- `tests/test_runtime_mutation_bypass_proof.py`
- `docs/runtime_mutation_sovereignty_proof.md`

## Proof results

### Canonical gateway exists

`core/runtime/runtime_mutation_gateway.py` declares `RuntimeMutationGateway.mutate` and blocks requests missing:

- `runtime_identity_required`
- `runtime_authority_scope_required`
- `runtime_capability_scope_required`

It also evaluates:

- runtime authority
- runtime capability scope
- kernel protection
- mutation policy

### Current bypass candidates are real

The proof tests show that these surfaces still exist outside the canonical gateway path:

- `core/runtime/mutation_patch_apply.py`
- `core/runtime/mutation_runtime_pipeline.py`
- `core/runtime/controlled_mutation_bridge.py`
- `core/runtime/runtime_ownership.py`

Current findings:

1. `mutation_patch_apply.py` performs direct file mutation operations such as copy/write behavior without importing `RuntimeMutationGateway` or `RuntimeMutationGuard`.
2. `mutation_runtime_pipeline.py` calls `apply_patch_plan` directly without entering `RuntimeMutationGateway`.
3. `controlled_mutation_bridge.py` routes a governed probe through `AgentExecutionRuntime`, not through `RuntimeMutationGateway`.
4. `runtime_ownership.py` still treats `RuntimeOwner.SYSTEM` as wildcard authority.

## Why this proof matters

The previous status authority seal answered:

> Who can write runtime task/status truth?

This proof starts the next boundary:

> Who can mutate files, source, rollback artifacts, and mutation side effects?

The current answer is not yet sovereign. There is a canonical gateway, but not all mutation surfaces are forced through it.

## Recommended next seal

Next: `Runtime Mutation Gateway Sovereignty Seal`.

Dependency order:

1. Make `RuntimeMutationGateway` the only production source/file mutation authority.
2. Convert `mutation_patch_apply.py` into a gateway-owned implementation detail or require a gateway-issued mutation authority token.
3. Convert `mutation_runtime_pipeline.py` into a gateway client rather than a direct mutation owner.
4. Keep `controlled_mutation_bridge.py` as a probe/client surface and explicitly prevent real source mutation outside the gateway.
5. Replace unrestricted `SYSTEM` wildcard access with a scoped issuer-token or explicit emergency-only authority.
6. Add final enforcement tests that fail on new direct mutation writers outside the gateway.

## Non-mainline issues

No unrelated functional defects were investigated or fixed in this package. The proof intentionally reports mutation sovereignty gaps but does not change production code.

## Validation

Executed locally against the prepared repository snapshot:

```text
pytest -q tests/test_runtime_mutation_gateway_sovereignty_seal.py tests/test_runtime_mutation_bypass_proof.py
8 passed
```
