# Governed Repair Transaction Proposal

## Purpose

The governed repair transaction proposal layer converts a repair recommendation into a scoped mutation proposal.

```text
repair recommendation
 -> governed repair transaction proposal
 -> governed mutation pipeline eligibility
```

This layer still does not mutate files or execute commands.

---

## Required Guarantees

The proposal must include:

- repair scope
- allowed mutation targets
- approval requirement
- rollback requirement
- verification requirement

It must not:

- apply patches
- execute repairs
- grant runtime authority
- claim canonical success

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
requires_governed_mutation_pipeline=True
requires_rollback_eligibility=True
requires_verification_before_success=True
```

---

## Forbidden Bypasses

Forbidden:

```text
repair proposal -> direct mutation
repair proposal -> direct shell execution
repair proposal -> canonical runtime success
repair proposal -> rollback claim without governed runtime
```

Any future mutation must still enter:

```text
governed repair transaction
 -> mutation pipeline
 -> verification
 -> evidence
 -> rollback/recovery eligibility
```

---

## Future Extension Path

Future work may add:

- repair diff planning
- scoped rollback plans
- approval signatures
- mutation transaction IDs
- verification command linkage
- repair budgeting
- escalation workflows

Future implementation must preserve the L4 runtime freeze and governed execution boundaries.
