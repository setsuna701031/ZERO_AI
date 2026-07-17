# Runtime Mutation Sovereignty Closure

Status: enforcement closure package.

## Authority decision

`RuntimeMutationGateway` is the canonical mutation authority.  The gateway owns
risk classification, authority evaluation, capability evaluation, kernel
protection checks, mutation policy evaluation, transaction lifecycle, and
mutation provenance.

## Surface classification

| Surface | Role | Enforcement |
| --- | --- | --- |
| `core/runtime/runtime_mutation_gateway.py` | AUTHORITY | Owns mutation decisions and stamps mutation authority metadata. |
| `core/runtime/governed_mutation_runtime.py` | REQUEST | May request governed mainline mutation but must not own policy decisions. |
| `core/runtime/mutation_runtime_pipeline.py` | REQUEST | Issues a gateway-scoped mutation capability and passes it to persistence. |
| `core/runtime/mutation_patch_apply.py` | PERSISTENCE | Performs bounded file persistence only after validating mutation authority. |
| `core/runtime/controlled_mutation_bridge.py` | REQUEST | Probe-only bridge; it does not execute real source mutation. |

## Closure guarantees

- Mutation decision terms are retained in `RuntimeMutationGateway` only.
- Request clients no longer act as mutation authority owners.
- Patch persistence receives an explicit `mutation_capability` envelope.
- Missing capability is rejected by `require_runtime_mutation_authority`.
- SYSTEM wildcard authority remains sealed by the prior system authority seal.

## Remaining mutation writers

`mutation_patch_apply.py` still performs filesystem writes by design.  It is now
classified as PERSISTENCE rather than AUTHORITY, and writes are guarded by the
runtime mutation authority capability envelope.

## Remaining bypass paths

No covered bypass path owns mutation approval or risk decisions.  The controlled
bridge remains a probe-only execution path and does not perform source edits.

## Non-mainline issues

- Evidence reference ownership is still a separate distributed metadata surface.
- Rollback artifact ownership should remain under future evidence / rollback
  authority work instead of being folded into mutation decision ownership.
- Legacy direct unit tests for `apply_patch_plan` are supported by compatibility
  capability issuance, but production request paths should continue routing via
  `mutation_runtime_pipeline` or `RuntimeMutationGateway`.
