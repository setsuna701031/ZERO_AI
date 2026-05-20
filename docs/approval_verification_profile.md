# Approval Envelope and Verification Profile

## Purpose

The approval envelope and verification profile layer sits between diff proposal and any future governed patch application.

It formalizes:

```text
diff proposal
 -> approval envelope
 -> verification profile
 -> governed apply eligibility
```

without applying patches, executing subprocesses, or enabling autonomous mutation.

---

# Boundary

This layer is read-only and planning-only.

It may produce:

- approval_id
- proposal_id
- plan_id
- review_state
- authority_scope
- verification_profile_id
- verification commands
- retry budget
- rollback requirement
- recovery requirement
- governed apply eligibility marker

It must not produce:

- runtime_evidence_id
- runtime_audit_metadata
- governed_mutation_lineage
- verification_result
- rollback execution result
- recovery execution result
- canonical success marker

Those fields belong only to governed runtime execution and mutation flows.

---

# Approval Envelope

An approval envelope records the review state for a proposal.

Supported review states:

```text
pending
approved
rejected
```

Even an approved envelope is not patch execution. It only means the proposal may proceed to a future governed apply path.

---

# Verification Profile

A verification profile records the commands that must be run after a future governed apply.

The profile itself does not execute commands.

It requires:

```text
verification_execution_allowed=False
rollback_required=True
recovery_required=True
```

This keeps verification planning separate from runtime execution authority.

---

# Governed Apply Eligibility

Eligibility is not execution.

It only proves that:

- proposal id matches approval id
- proposal id matches verification profile id
- approval is approved
- verification commands exist
- rollback is required
- recovery is required

The result remains:

```text
mutation_allowed=False
execution_allowed=False
patch_apply_allowed=False
```

Actual apply must later enter the governed mutation/runtime spine.

---

# Forbidden Bypasses

Forbidden:

```text
approval -> direct patch apply
approval -> raw subprocess
verification profile -> direct execution
eligibility -> canonical success
planner -> execution authority
proposal -> mutation success
```

---

# Future Extension Path

Future production enablement may add:

- approval UI
- verification command router
- governed apply wrapper
- retry/repair budget enforcement
- rollback plan generation
- recovery plan generation
- evidence/audit capture after governed apply

These future surfaces must preserve:

- runtime authority ownership
- governed mutation lineage
- sealed evidence/audit lineage
- rollback/recovery eligibility
- L4 runtime freeze contracts
