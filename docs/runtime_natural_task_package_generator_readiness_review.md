# Runtime Natural Task Package Generator Readiness Review

## Purpose

This review seals the first natural-language intake boundary for ZERO runtime operation. The generator converts one operator-provided task sentence into a deterministic runtime operator package. It does not execute the package and does not bypass the existing operator console or runtime operator service.

## Scope

Package: Runtime Natural Task Package Generator

Files:

- `core/runtime/runtime_natural_task_package_generator.py`
- `tests/test_runtime_natural_task_package_generator.py`
- `docs/runtime_natural_task_package_generator_readiness_review.md`

Validation command:

```powershell
python -m pytest tests/test_runtime_natural_task_package_generator.py -q
```

## Boundary

The generator owns only this path:

```text
natural task text
    ↓
deterministic runtime operator package
```

The generator does not own this path:

```text
runtime operator package
    ↓
operator console
    ↓
runtime operator service
    ↓
executor gate
    ↓
controlled mutation
```

That downstream path is already owned by the existing operator console and runtime service chain.

## Required Package Shape

Generated packages must use schema:

```text
zero.runtime.operator_package.v1
```

Every generated package must include:

- `package_id`
- `task_id`
- `goal`
- `requested_mode`
- `target_root`
- `requested_changes`
- `authority_context`
- `validation_required`
- `rollback_required`

## Safety Rules

The generator must not:

- call the executor
- open an invocation gate
- dispatch runtime work
- start execution
- mutate runtime state
- write files
- read repository state
- call subprocesses
- call git
- call scheduler
- call operator console
- call runtime operator service
- bypass the operator service
- bypass controlled execution
- disable validation
- disable rollback

## Determinism Rules

The generator must:

- normalize task text by trimming surrounding whitespace
- produce stable `task_id` values from canonical package input
- produce stable `package_id` values from canonical package input
- preserve requested changes by value
- preserve authority context by value
- return plain dictionaries only

## Downstream Handoff

The generated package is intended for the existing controlled command path:

```powershell
python -m cli.zero_operator_console run <generated-package-json> --controlled
```

This review does not add a CLI command for generation. A future package may wire this helper into an operator console command after this pure boundary remains sealed.

## Readiness Decision

GO.

The boundary is ready when the focused test proves that natural task text can be transformed into a deterministic controlled runtime operator package while preserving all no-execution and no-bypass requirements.

## Next Package

Recommended next package:

```text
Runtime Natural Task Console Bridge
```

That future package may add a console command that writes or displays the generated package, but it must still avoid direct execution unless explicitly routed through the existing controlled operator console path.
