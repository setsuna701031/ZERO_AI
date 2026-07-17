
## Package 168

Package 168: Runtime Natural Task CLI Bridge

Package 168 adds a planning-only CLI bridge from natural task text to generated runtime operator package and controlled operator console command plan.

Package 168 owns:

- `core/runtime/runtime_natural_task_cli_bridge.py`
- `cli/zero_natural_task_package_generator.py`
- `tests/test_runtime_natural_task_cli_bridge.py`
- `docs/runtime_natural_task_cli_bridge_readiness_review.md`
- deterministic bridge result from natural task text
- deterministic generated runtime operator package handoff
- deterministic command plan for controlled operator console execution
- CLI JSON output for full bridge payload or summary

Package 168 must not:

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
- collapse package generation, package file writing, and execution into one step

Validation expectation:

- focused tests must prove the bridge builds a package and command plan only
- focused tests must prove the CLI prints JSON only
- focused tests must prove no runtime execution or IO boundary is imported or invoked

Final decision: GO for planning-only CLI bridge. Next package: Package 169 package JSON writer boundary.
