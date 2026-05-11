# Persistence Kernel Contract

## Purpose

This document defines the current persistence kernel contract inside:

```text
core/tasks/scheduler.py
```

Primary kernel function:

```text
_persist_task_payload
```

Phase10 treats persistence as a runtime durability boundary, not a simple helper.

---

## Current kernel role

The persistence kernel is responsible for durable runtime state preservation.

It currently protects:

- task identity
- runtime state continuity
- execution history
- public snapshot consistency
- restart/recovery compatibility
- queue rebuild compatibility

This kernel should not be treated as cleanup code.

---

## Persistence guarantees

The persistence kernel currently guarantees:

### Identity preservation

The following fields must survive persistence:

- `task_id`
- `task_name`
- `goal`
- `status`

### Runtime continuity

The following runtime-related fields must remain stable:

- `runtime_state_file`
- `results`
- `step_results`
- `execution_log`

### Public snapshot continuity

Persistence should preserve or refresh:

```text
public_snapshot
```

### Restart compatibility

Persistence should not corrupt:

- runtime state recovery
- hydration behavior
- queue restoration
- restart resume behavior

---

## Forbidden extraction mistakes

Do not:

1. Move persistence into generic file utilities.
2. Mix planner logic into persistence.
3. Mix repair policy into persistence.
4. Rewrite runtime_state_file semantics casually.
5. Remove execution history during persistence.
6. Optimize persistence for line count only.
7. Split persistence before persistence contract tests exist.

---

## Phase10 persistence contract tests

Current contract test file:

```text
tests/test_persistence_runtime_contract.py
```

The tests currently verify:

- identity preservation
- runtime file preservation
- public snapshot continuity
- missing optional field handling
- result/step_result persistence

---

## Future extraction direction

Possible future target:

```text
core/tasks/scheduler_core/task_persistence_runtime.py
```

But extraction should only happen after:

- persistence contract tests are stable
- hydration compatibility is stable
- restart/recovery tests exist
- repo write semantics are documented
- runtime snapshot format is stable

---

## Current architectural interpretation

At Phase10, persistence is considered:

```text
runtime durability kernel
```

not:

```text
cleanup helper
```
