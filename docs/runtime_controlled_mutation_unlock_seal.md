# Runtime Controlled Mutation Unlock Seal

The controlled mutation unlock is sealed as the final closure bundle for the controlled autonomous runtime loop.

The executor cannot mutate directly. It may only produce a controlled real executor result, after which `RuntimeOperatorService` invokes the governed mutation adapter. All mutation is sandbox governed by the existing repo edit, validation, rollback, and commit boundary.

Rollback is mandatory. Validation failure must produce `rollback_required=True`, `rollback_completed=True`, and `commit_allowed=False`.

Commit requires validation. The success path requires `mutation_allowed=True`, `mutation_started=True`, `validation_passed=True`, `rollback_required=False`, and `commit_allowed=True`.

The expected closed-loop status is `real_executor_ready=True`, `real_executor_enabled=True`, `execution_real=True`, `mutation_allowed=True`, `controlled_mutation=True`, `rollback_available=True`, `validation_required=True`, and `autonomous_runtime_loop_closed=True`.
