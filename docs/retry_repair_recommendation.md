# Retry / Repair Recommendation Contract

## Purpose

The retry / repair recommendation layer consumes a verification evidence bundle and recommends the next control-plane action.

```text
verification evidence
 -> retry/repair recommendation
 -> retry, repair, escalation, or no-action decision
```

This layer does not retry, repair, mutate, approve, execute, or claim runtime success.

---

## Decisions

Supported decisions:

- `no_action`
- `retry_verification`
- `retry_then_review`
- `recommend_repair`
- `escalate_to_user`
- `hard_stop`

The recommendation is conservative. It is a routing hint, not an automatic mutation grant.

---

## Retry Budget

The recommendation carries:

```text
attempt_index
max_retries
retries_remaining
```

Timeout and unknown failures prefer retry before escalation.

Test, compile, lint, and runtime failures may become repair recommendations after the retry budget is exhausted.

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
requires_governed_repair_transaction_for_mutation=True
```

This preserves the separation between:

- planning/recommendation control plane
- governed mutation plane
- runtime execution plane

---

## Forbidden Bypasses

Forbidden:

```text
recommendation -> direct repair
recommendation -> direct mutation
recommendation -> direct retry execution
recommendation -> runtime authority
recommendation -> canonical success
```

Any future repair execution must enter the governed repair transaction / mutation / runtime spine.

---

## Future Extension Path

Future work may add:

- richer failure confidence
- flaky test detection
- retry budgets per command
- user-review escalation UI
- governed repair transaction creation
- repair/retry memory
- evidence persistence

Future implementation must preserve L4 runtime freeze and governed self-edit boundaries.
