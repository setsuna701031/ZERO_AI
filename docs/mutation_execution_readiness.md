# Mutation Execution Readiness Contract

## Purpose

Mutation execution readiness determines whether a governed repair transaction proposal has enough gates to be submitted to the governed mutation pipeline.

```text
repair transaction proposal
 -> mutation execution readiness
 -> governed mutation pipeline eligibility
```

This layer still does not mutate files, execute commands, apply patches, or claim runtime success.

---

## Required Gates

A proposal is ready only when all of these are true:

- approval is complete
- rollback is available
- verification profile is available
- mutation scope is locked
- allowed mutation targets are explicit

If any gate is missing, readiness is blocked.

---

## Boundary

Required metadata:

```text
control_plane_only=True
read_only=True
mutation_allowed=False
execution_allowed=False
patch_apply_allowed=False
runtime_authority_granted=False
canonical_runtime_success=False
governed_mutation_pipeline_required=True
requires_runtime_evidence_after_execution=True
requires_audit_lineage_after_execution=True
```

Readiness is only an eligibility artifact. It is not execution authority.

---

## Blockers

Known blockers:

- approval_incomplete
- rollback_unavailable
- verification_profile_unavailable
- mutation_scope_unlocked

---

## Forbidden Bypasses

Forbidden:

```text
readiness -> direct mutation
readiness -> direct execution
readiness -> canonical success
readiness -> runtime evidence claim
readiness -> audit lineage claim
```

Only the governed runtime may produce runtime evidence and audit lineage after execution.

---

## Future Extension Path

Future work may add:

- approval signatures
- rollback snapshot references
- verification profile IDs
- mutation transaction IDs
- scoped write guards
- governed apply wrappers
- regression coverage around real apply transactions

Future implementation must preserve L4 runtime freeze, governed self-edit gates, and runtime authority ownership.
