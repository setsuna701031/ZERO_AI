## Package 167

Package 167: Runtime Natural Task Package Generator

Scope:

Package 167 creates the first natural-language task intake boundary for ZERO runtime operation. It converts a single natural-language task into a deterministic runtime operator package and does not execute, dispatch, mutate, persist, or bypass the operator service.

Files:

- `core/runtime/runtime_natural_task_package_generator.py`
- `tests/test_runtime_natural_task_package_generator.py`
- `docs/runtime_natural_task_package_generator_readiness_review.md`

Validation command:

- `python -m pytest tests/test_runtime_natural_task_package_generator.py -q`

Package 167 owns:

- natural task text intake
- deterministic runtime operator package generation
- `zero.runtime.operator_package.v1` output shape
- package id generation
- task id generation
- goal preservation
- requested controlled mode
- target root preservation
- requested changes preservation by value
- authority context preservation by value
- validation required flag
- rollback required flag
- no-dispatch output status
- no-execution output status
- no-runtime-mutation output status

Package 167 must not:

- execute runtime work
- call executor
- open invocation gate
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
- persist
- replay
- audit
- journal
- bypass operator service
- bypass controlled execution
- disable validation
- disable rollback
- run broad validation

GO / NO-GO:

Final decision: GO.

Next package: Package 168.

## Non-mainline Issues Found

- Package 139 contract prose still contains older schema field names that differ from the Package 140 validation shape. Package 167 preserves the previously reported documentation drift and does not modify Package 139.
- Pre-existing untracked AER governance/runtime/docs/tests files and package sequence edits may exist in the worktree. Package 167 preserves unrelated worktree noise and changes only the requested natural task package generator helper, focused test, readiness review, and package sequence entry.
