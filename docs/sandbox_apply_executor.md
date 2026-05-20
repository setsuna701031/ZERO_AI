# Sandbox Apply Executor Contract

## Purpose

The sandbox apply executor is the first dry-run mutation boundary after the governed apply wrapper.

```text
governed apply request
 -> sandbox apply dry run
 -> rollback checkpoint draft
 -> verification draft
 -> evidence draft
```

This phase does not write files or execute commands. It prepares the structural envelope for future controlled repository mutation.

---

## Required Boundary

The dry-run result must include:

```text
dry_run=True
sandbox_only=True
no_real_write=True
mutation_allowed=False
execution_allowed=False
patch_apply_allowed=False
runtime_authority_granted=False
canonical_runtime_success=False
```

It also requires:

- rollback checkpoint draft
- verification draft
- evidence draft
- target files
- planned operations

---

## What This Layer Does

This layer may:

- validate an apply request shape
- confirm sandbox/dry-run requirements
- draft rollback checkpoint requirements
- draft verification requirements
- draft evidence/audit requirements
- report blockers

---

## What This Layer Does Not Do

This layer does not:

- apply patches
- write files
- run subprocesses
- create real rollback checkpoints
- run verification commands
- create runtime evidence
- claim canonical success

---

## Forbidden Bypasses

Forbidden:

```text
sandbox dry run -> real write
sandbox dry run -> raw subprocess
sandbox dry run -> runtime authority
sandbox dry run -> canonical success
sandbox dry run -> evidence seal
```

Only the governed runtime / mutation pipeline may perform real mutation and create sealed evidence.

---

## Future Extension Path

Future work may add:

- isolated temp workspace apply
- real dry-run patch validation
- rollback snapshot creation
- post-apply verification replay
- governed runtime evidence sealing
- mutation commit summary
- interactive user approval UI

Future implementation must preserve the L4 runtime freeze and engineering workflow boundaries.
