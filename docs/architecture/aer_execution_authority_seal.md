# AER Execution Authority Seal

## Status

Sealed.

## Formal Execution Authority Paths

The only formal execution chains are:

```text
AgentLoop -> AgentExecutionRuntime -> TaskRunner -> StepExecutor
CodeChainControlledSelfEditBridge -> AgentExecutionRuntime -> TaskRunner -> StepExecutor
ControlledMutationBridge -> AgentExecutionRuntime -> TaskRunner -> StepExecutor
Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor
```

## Ownership Contract

- AgentLoop is orchestration/admission only.
- AgentExecutionRuntime owns runtime execution authority.
- RuntimeDispatcher is the required Scheduler execution handoff and live capability issuer.
- TaskRunner is the required delegation boundary.
- StepExecutor is the endpoint only.
- Scheduler may wire dependencies during initialization, but RuntimeDispatcher is its only legal execution handoff and Scheduler must not directly execute steps.
- Bridges must not own execution authority.

## Forbidden Paths

```text
AgentLoop -> StepExecutor
AgentLoop -> TaskRunner -> StepExecutor
Bridge -> StepExecutor
Bridge -> execute_step
Bridge -> execute_steps
EngineeringTaskRunner direct route from AgentLoop
```

## Required Audit Flags

Runtime-owned execution payloads must report:

```text
direct_execution=False
agent_loop_owns_execution=False
runtime_owns_execution=True
taskrunner_required=True
step_executor_endpoint_only=True
```

## Non-Mainline Issue Reporting

Any future direct execution, authority drift, contract drift, or hidden bridge must be reported explicitly.
It must not be silently bypassed, renamed, or hidden behind compatibility shims.
