# Verification Evidence Bundle

## Purpose

The verification evidence bundle is the structured result layer after verification command routing.

It converts a verification-only command result into a stable planning artifact for future retry/repair logic.

```text
verification route
 -> command result
 -> verification evidence bundle
 -> failure classification
 -> retry/repair eligibility
```

This layer does not execute commands. It only records the result of a command that was already routed as verification-only.

---

## Boundary

The bundle is read-only and non-mutating.

Required metadata:

```text
verification_only=True
read_only=True
mutation_allowed=False
execution_authority_granted=False
patch_apply_allowed=False
canonical_runtime_success=False
feeds_retry_repair_loop=True
```

A verification evidence bundle cannot be treated as canonical governed runtime success.

---

## Failure Classification

Initial classifications:

- none
- test_failure
- compile_failure
- lint_failure
- timeout
- runtime_error
- unknown_failure

These classifications are intentionally conservative. They are routing hints for a future retry/repair loop, not proof that repair should execute automatically.

---

## Retry / Repair Eligibility

Retry may be recommended for:

- test failure
- compile failure
- lint failure
- timeout
- runtime error
- unknown failure

Repair eligibility is narrower and excludes timeout by default because a timeout may be environmental rather than code-related.

---

## Forbidden Bypasses

Forbidden:

```text
verification result -> canonical runtime success
verification result -> direct mutation
verification result -> direct patch apply
verification result -> runtime authority
verification result -> rollback/recovery claim
```

Rollback and recovery eligibility must be produced by governed mutation/runtime layers, not by this verification evidence layer.

---

## Future Extension Path

Future work may add:

- richer pytest parsing
- compile error extraction
- timeout budgets
- retry budgets
- repair recommendation routing
- evidence persistence
- integration with governed repair transactions

Any future extension must preserve the L4 runtime freeze invariants.
