# Runtime Mutation Closure

Schema: `zero.runtime_mutation_closure.v1`

## Purpose

This closure seals the runtime mutation exit path after authority, capability,
identity, evidence, persistence, and ownership have already been canonicalized.
It does not grant authority and it does not execute mutations. It validates that
a mutation request and every downstream mutation record preserve one canonical
mutation graph.

## Canonical graph

A mutation is valid only when the same graph is preserved across request,
authority, capability, identity, ownership, mutation execution, evidence,
persistence, and resume records:

- `mutation_request_id`
- `mutation_id`
- `authority_decision_id`
- `capability_id`
- `execution_id`
- `identity_fingerprint`
- `ownership_fingerprint`
- `evidence_id`
- `persistence_id`

## Closed chain

```text
Mutation Request
        ↓
Authority Check
        ↓
Capability Check
        ↓
Identity Check
        ↓
Ownership Check
        ↓
Mutation Execution
        ↓
Evidence Record
        ↓
Persistence Record
        ↓
Resume Validation
```

## Enforced invariants

1. No mutation without an authority decision.
2. No mutation without a capability.
3. No mutation without identity.
4. No mutation without ownership.
5. Mutation evidence must preserve the same mutation graph.
6. Mutation persistence must preserve the same mutation graph.
7. Resume must not remint or replace mutation identity.
8. Direct or ungoverned mutation bypass markers are rejected.
9. Existing mutation fields may only match the canonical graph; they may not
   override it.

## Non-mainline findings

Mandatory reporting remains active. During this closure pass, the package keeps
legacy mutation-sovereignty and mutation-authority materials as non-mainline
historical references. Any future discovery of direct mutation paths,
parallel mutation authorities, hidden mutation fallbacks, or mutation/evidence /
persistence drift must be recorded here rather than silently ignored.

Known watch areas:

- `runtime_mutation_gateway.py`
- `governed_mutation_runtime.py`
- legacy mutation sovereignty documentation
- direct file mutation helpers outside the governed runtime path

These are watch items unless a concrete drift path is discovered in a runtime
closure test or audit scan.
