# Runtime execution authority closure audit

## Decision

The only execution endpoints are `StepExecutor.execute_step`, `StepExecutor.execute_steps`, `execution_gateway.safe_subprocess_run`, and `Executor.execute_request`. Every other execute/run/dispatch surface is an issuer, delegator, dispatcher, policy gate, or descriptive projection. Authority metadata is evidence only: it cannot grant execution, synthesize approval, or replace a live runtime capability.

## Canonical execution authority matrix

| Surface | Role | May execute | Gate | Live capability |
| --- | --- | ---: | ---: | ---: |
| `RuntimeDispatcher.dispatch/resume/run_scheduler_boundary` | issue and dispatch | no | before endpoint | issues |
| `TaskRunner.run/run_task/run_one_tick/run_one_step` | compatibility delegation | no | required | required |
| `TaskRunner._run_one_step` | pre-execution delegation | no | required | validates and delegates |
| `TaskRuntime` read-only command/replay gates | bounded dispatch | no | required | not required; whitelist-bound |
| `StepExecutor.execute_step/execute_steps` | execution endpoint | yes | required | required for privileged execution |
| `execution_gateway.safe_subprocess_run` | process endpoint | yes | required | gateway-owned |
| `Executor.execute_request` | governed execution endpoint | yes | required | gateway-owned |
| `runtime_native_execution_path` | descriptive projection | no | n/a | n/a |

The machine-readable matrix is `CANONICAL_EXECUTION_AUTHORITY_MATRIX`; the callable inventory is `EXECUTION_AUTHORITY_INVENTORY`.

## Scoped-file inventory

- `execution_authority.py`: validates metadata but rejects compatibility/descriptive metadata as authority. It no longer invents `approved` or an allowed policy result.
- `runtime_execution_authority_gate.py`: policy enforcement only; it never executes work.
- `runtime_execution_authority_policy.py`: finite owner/action matrix. Side-effect actions include execute, run, and dispatch.
- `runtime_native_execution_authority.py`: publishes the canonical matrix and explicitly requires gate and capability validation.
- `runtime_dispatcher.py`: issues live task/package/session capabilities and delegates to TaskRunner; `direct_execution=False`.
- `task_runner.py`: validates and delegates the live capability, invokes the execution authority gate immediately before StepExecutor and subprocess verification paths, and preserves SYSTEM capability lineage through the active late-bound authority builder.
- `task_runtime.py`: internal `pwd/dir/ls` operations remain in-process; subprocess-backed read-only and replay operations invoke the authority gate before the canonical gateway.

## Bypass findings and closure

| Finding | Severity | Closure |
| --- | --- | --- |
| metadata could synthesize approval and an allowed policy result | critical | compatibility metadata is descriptive-only and fails authority validation |
| late TaskRunner monkey-patch dropped SYSTEM capability | critical | SYSTEM capability now propagates in success and denial contexts |
| TaskRunner regression verification called the subprocess gateway without the authority gate | high | explicit gate enforcement precedes every call |
| TaskRuntime read-only execution and replay called the subprocess gateway without the authority gate | high | explicit gate enforcement precedes both calls |
| native execution authority was descriptive but did not expose the enforced matrix | medium | native contract now embeds the canonical matrix and enforcement requirements |
| source strings can describe canonical ownership | medium | source policy alone performs no execution; real privileged execution still requires the live in-process capability at TaskRunner/StepExecutor |

## Failure contract

Missing live capability fails before StepExecutor with `execution_authority_denied`. A non-canonical side-effect source fails in `RuntimeExecutionAuthorityGate` with `RuntimeExecutionAuthorityDenied`. Descriptive or compatibility metadata fails validation with `authority_metadata_is_not_execution_authority`. No denied path invokes an execution endpoint.
