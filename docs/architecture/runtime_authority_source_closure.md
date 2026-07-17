# Runtime Authority Source Closure

Schema: `zero.runtime_authority_source_closure.v1`

This audit closes the runtime execution-authority source boundary.

Canonical chain:

```text
RuntimeExecutionAuthorityPolicy
→ RuntimeCapabilityTokenManager
→ Runtime Action
```

## Rules

1. `RuntimeExecutionAuthorityPolicy` is the only execution-authority decision source.
2. RuntimeCapabilityTokenManager is not execution authority. It only issues and validates scoped proof tokens after an authority decision.
3. `runtime_dispatcher`, `task_runner`, `task_runtime`, mutation gateway, and governed mutation runtime may carry authority metadata, but must not create a stronger execution authority decision.
4. Runtime side effects must not be allowed by implicit checks such as `is_admin`, `trusted`, `privileged`, runtime-zone equality, fallback authority, or wildcard authority.
5. Metadata that says `authority_status=allowed` is not sufficient proof of execution authority unless it is backed by the canonical policy decision and required capability proof.

## Non-mainline issue reporting

Mandatory reporting applies to discovered issues even when they are outside the active repair scope. Report, do not silently skip:

- parallel authority system
- hidden capability source
- fallback authority
- wildcard authority
- ownership/authority mixed responsibility
- evidence/authority mixed responsibility

## Observed non-mainline surfaces to track

These are not fixed by this package, but they are explicitly listed so they cannot be silently ignored:

- `core/runtime/runtime_mutation_gateway.py` uses `RuntimeAuthorityEvaluator` for mutation authority scope. This must remain separated from execution authority or later be bridged through `RuntimeExecutionAuthorityPolicy`.
- `core/runtime/runtime_dispatcher.py` carries execution authority metadata. This metadata must remain propagation evidence, not an independent grant source.

## Audit target files

```text
core/runtime/runtime_dispatcher.py
core/runtime/task_runner.py
core/runtime/task_runtime.py
core/runtime/runtime_mutation_gateway.py
core/runtime/governed_mutation_runtime.py
core/runtime/runtime_execution_authority_policy.py
core/runtime/runtime_capability_tokens.py
```
