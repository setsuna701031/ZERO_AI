# Repair Kernel Contract

## Purpose

This document defines the current repair kernel contract inside:

```text
core/tasks/scheduler.py
```

Primary kernel function:

```text
_is_repairable_failure
```

Phase10 treats repair behavior as runtime policy, not cleanup code.

---

## Current kernel role

The repair kernel decides whether a failed task is allowed to enter repair or replan behavior.

It protects the runtime from unsafe or meaningless repair attempts.

---

## Repair decision inputs

The repair kernel currently considers:

- task payload validity
- task status
- `replan_count`
- `max_replans`
- failed step type
- hard failure text
- verify-step repair policy

---

## Repair guarantees

### Non-repairable status is rejected

Tasks outside repairable states should not enter repair.

Repairable status set currently includes:

```text
failed
error
queued
```

### Replan budget is enforced

If:

```text
replan_count >= max_replans
```

then repair must be rejected.

### Unsupported step types are rejected

Repair should only allow known repairable step types.

### Hard failures are rejected

Hard failure text should prevent repair/replan loops.

Examples include:

- unsupported step type
- invalid step type
- depends_on task not found
- self dependency
- task already terminal
- file not found
- no such file
- path not found

### Verify failures use verify policy

Verify failures must pass through dedicated verify-step repairability logic.

---

## Forbidden extraction mistakes

Do not:

1. Move repair policy into generic helpers.
2. Mix repair policy with planner fallback logic.
3. Mix repair policy with persistence.
4. Allow repair loops when budget is exhausted.
5. Retry hard failures that should stay terminal.
6. Treat all verify failures as repairable.
7. Extract `_is_repairable_failure` without dedicated repair tests.

---

## Phase10 repair contract tests

Current contract test file:

```text
tests/test_repair_kernel_contract.py
```

The tests verify:

- non-repairable status rejection
- replan budget rejection
- unsupported step rejection
- hard failure rejection
- recoverable write_file failure acceptance
- recoverable command failure acceptance
- verify failure routing through verify policy

---

## Future extraction direction

Possible future target:

```text
core/tasks/scheduler_core/repair_policy_helpers.py
```

Extraction should only happen after:

- repair contract tests are stable
- replan behavior tests are stable
- verify policy behavior is covered
- failure classification is documented
- planner and persistence remain outside repair policy

---

## Current architectural interpretation

At Phase10, repair is considered:

```text
runtime repair policy kernel
```

not:

```text
cleanup helper
```
