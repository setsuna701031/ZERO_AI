# Runtime SYSTEM Authority Enforcement Seal

## Summary

`RuntimeOwner.SYSTEM` is no longer a wildcard runtime policy authority.

The previous policy granted `SYSTEM` access to every declared `RuntimeResource` and `RuntimeAction` through an unconditional branch in `core/runtime/runtime_ownership.py`. That branch could bypass the normal owner graph and the mutation guard.

This seal changes SYSTEM from a universal authority into an explicit, scoped owner. SYSTEM remains available for metadata and bootstrap/observability use, but it cannot mutate queue state, write execution results, dispatch orchestration, write repair state, or replay by default.

## Canonical rule

SYSTEM authority is now represented by `system_authority_rules()` and the private `_SYSTEM_ALLOWED_RULES` set in `core/runtime/runtime_ownership.py`.

Allowed by default:

- read declared runtime resources
- emit runtime events
- emit runtime incidents
- create runtime snapshots

Denied by default:

- queue writes and transitions
- execution-result writes
- orchestration dispatch
- repair-state writes
- replay actions
- any undeclared resource/action pair

## Boundary

Domain-specific private issuer tokens remain the authority path for live dispatcher, task-runner, scheduler, completion, and evidence actions. SYSTEM metadata strings such as `identity_type: SYSTEM` are not policy authority.

## Proofs

The enforcement tests prove:

1. `RuntimeOwner.SYSTEM` no longer grants all resource/action combinations.
2. `RuntimeMutationGuard` inherits the scoped behavior from `can_access`.
3. Mutation boundary requests reject SYSTEM writes/transitions/dispatches by default.
4. SYSTEM observability operations remain available.
5. The old wildcard implementation pattern is absent.
6. Existing mutation sovereignty proof tests continue to pass.

## Non-mainline issue report

A previous audit document was committed under `tests/runtime_system_authority_audit.md`. The canonical documentation location is `docs/`. This package adds the enforcement document under `docs/`; moving the historical audit file can be done in a cleanup-only documentation package if desired.
