# Governed Apply Wrapper Contract

## Purpose

The governed apply wrapper turns a fully gated mutation readiness artifact into a request envelope for a future governed mutation executor.

```text
mutation readiness
 -> governed apply request
 -> sandbox / dry-run / rollback / verification requirements
```

This layer still does not apply patches, write files, execute commands, or claim canonical runtime success.

---

## Required Gates

The request may only be built when readiness says:

```text
ready_for_governed_mutation=True
approval_complete=True
rollback_available=True
verification_profile_available=True
mutation_scope_locked=True
```

The request requires:

- dry run
- sandbox apply
- rollback checkpoint
- post-apply verification
- governed runtime execution
- runtime evidence after execution
- audit lineage after execution

---

## Boundary

Required metadata:

```text
control_plane_only=True
request_only=True
mutation_allowed=False
execution_allowed=False
patch_apply_allowed=False
runtime_authority_granted=False
canonical_runtime_success=False
requires_governed_runtime_execution=True
requires_sandbox_apply=True
requires_rollback_checkpoint=True
requires_verification_after_apply=True
requires_runtime_evidence_after_execution=True
requires_audit_lineage_after_execution=True
```

This is a request envelope, not an execution result.

---

## Forbidden Bypasses

Forbidden:

```text
apply request -> direct patch apply
apply request -> raw file write
apply request -> shell execution
apply request -> runtime evidence claim
apply request -> canonical success claim
```

Only the governed runtime / mutation pipeline may perform actual mutation and produce evidence.

---

## Future Extension Path

Future work may add:

- sandbox apply implementation
- dry-run diff validation
- rollback snapshot creation
- scoped file write guards
- post-apply verification execution
- evidence/audit sealing
- interactive approval UI

Future implementation must preserve runtime authority ownership and L4 freeze contracts.
