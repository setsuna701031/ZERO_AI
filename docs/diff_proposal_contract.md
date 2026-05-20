# Diff Proposal Contract

## Purpose

The diff proposal layer is the first non-mutating engineering workflow surface above:

- repo scan
- impacted file planning
- interactive engineering loop characterization
- governed self-edit characterization

This layer exists to formalize:

```text
impacted plan
 -> diff proposal object
 -> approval gate
 -> governed mutation eligibility
```

without enabling autonomous patch application.

---

# Read-Only Guarantee

Diff proposals:

- do not mutate files
- do not apply patches
- do not execute subprocesses
- do not claim runtime authority
- do not claim governed mutation success
- do not produce runtime evidence

Required metadata:

```text
read_only=True
mutation_allowed=False
execution_allowed=False
patch_apply_allowed=False
approval_required=True
```

---

# Intended Workflow Position

The intended future engineering loop is:

```text
task
 -> repo scan
 -> impacted file plan
 -> diff proposal
 -> approval/authority gate
 -> governed mutation request
 -> governed apply transaction
 -> verification
 -> evidence/audit lineage
 -> rollback/recovery eligibility
 -> summary/report
```

The diff proposal layer stops before governed mutation.

---

# Canonical Proposal Shape

A valid diff proposal includes:

- proposal_id
- plan_id
- task
- classified files
- proposed operations
- proposal summary
- approval-required metadata

A proposal must NOT include:

- runtime_evidence_id
- runtime_audit_metadata
- governed_mutation_lineage
- verification_result
- rollback_eligibility
- recovery_eligibility
- canonical execution success markers

Those fields only belong to governed execution flows.

---

# Forbidden Bypasses

Forbidden:

```text
planner -> direct write
planner -> raw subprocess
proposal -> implicit apply
proposal -> execution authority
proposal -> mutation success
```

The proposal layer is planning-only.

---

# Future Extension Path

Future safe extensions may include:

- structured diff previews
- semantic impacted analysis
- approval wrappers
- governed apply wrappers
- verification routing
- rollback planning
- repair/retry budgeting

Future extensions must preserve:

- runtime authority ownership
- governed mutation lineage
- evidence/audit continuity
- rollback/recovery guarantees
- topology freeze contracts

---

# Non-Goals

This layer does NOT:

- enable autonomous self-edit
- apply patches
- execute runtime mutations
- bypass governed runtime
- replace repair transactions
- replace runtime authority ownership
