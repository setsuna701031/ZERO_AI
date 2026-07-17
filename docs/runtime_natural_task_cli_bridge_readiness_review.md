# Runtime Natural Task CLI Bridge Readiness Review

## Purpose

Package 168 adds a planning-only CLI bridge between the Package 167 natural task package generator and the existing controlled operator console command shape.

The bridge prepares a deterministic runtime operator package and a deterministic command plan. It does not write package JSON, start the operator console, dispatch execution, invoke an executor, mutate runtime state, validate a repository, or commit changes.

## Package 168 Scope

Package 168 owns:

- `core/runtime/runtime_natural_task_cli_bridge.py`
- `cli/zero_natural_task_package_generator.py`
- `tests/test_runtime_natural_task_cli_bridge.py`
- this readiness review
- a planning-only handoff from natural task text to generated runtime package and operator console command plan

## Boundary

The bridge may:

- call `build_runtime_operator_package_from_task(...)`
- validate the generated package with the Package 167 validator
- create a command plan for `python -m cli.zero_operator_console run <package_json> --controlled`
- print JSON from the CLI generator

The bridge must not:

- call `RuntimeOperatorService`
- call `run_goal(...)`
- call `run_package(...)`
- start `zero_operator_console`
- write package JSON files
- open files
- inspect the repository
- start subprocesses
- request network access
- invoke an executor
- start execution
- mutate runtime state
- commit changes

## Output Contract

`build_natural_task_cli_bridge(...)` returns a deterministic dict containing:

- `schema`
- `ok`
- `bridge_status`
- `runtime_operator_package`
- `package_validation`
- `package_summary`
- `command_plan`
- `package_json_written: false`
- `operator_console_started: false`
- `executor_invoked: false`
- `execution_started: false`
- `task_executed: false`
- `runtime_state_mutated: false`

## CLI Contract

`python -m cli.zero_natural_task_package_generator "<task>"` prints the bridge payload as JSON.

`--summary` prints only the stable summary.

The CLI is a package generator interface only. It is not the executor CLI.

## Readiness Decision

GO for planning-only CLI bridge.

NO-GO for automatic execution, package JSON file writing, direct operator console invocation, daemon mode, repository mutation, or commit behavior in this package.

## Next Package

Package 169 should add a package JSON writer boundary if needed. That package must remain separate from execution.
