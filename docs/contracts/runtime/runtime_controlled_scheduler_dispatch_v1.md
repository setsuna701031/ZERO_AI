# Runtime Controlled Scheduler Dispatch Bundle v1

## Purpose

This contract defines the controlled data path from dispatch admission to executor handoff readiness.

The bundle does not execute work. It only proves that an admitted wake can move through dispatch bridge, runnable selection admission, and executor handoff permission.

## Inputs

- RuntimeSchedulerDispatchAdmissionRecord
- Optional injected dispatch handler
- RuntimeSchedulerDispatchBridgeRecord
- RuntimeRunnableSelectionRecord

## Outputs

### RuntimeSchedulerDispatchBridgeRecord

Required fields:

- dispatch_bridge_authorized
- source_dispatch_admission_id
- dispatch_handler_called
- dispatch_result_received
- selected_work_id
- denial_reason
- executor_invoked
- runtime_state_mutated

### RuntimeRunnableSelectionRecord

Required fields:

- runnable_selection_authorized
- selected_work_id
- source_dispatch_bridge_id
- denial_reason
- executor_invoked
- runtime_state_mutated

### RuntimeExecutorHandoffRecord

Required fields:

- executor_handoff_authorized
- handoff_work_id
- source_selection_id
- executor_called
- execution_started
- runtime_state_mutated
- denial_reason

## Rules

- Dispatch bridge requires an authorized dispatch admission record.
- Dispatch bridge may call only an injected dispatch handler.
- The injected dispatch handler receives only admission data.
- Runnable selection requires an authorized bridge and a selected work id.
- Executor handoff requires an authorized runnable selection.
- Executor handoff does not call executor.
- No layer in this bundle mutates runtime state.

## Denials

Denials must be deterministic for:

- missing dispatch admission
- rejected dispatch admission
- handler failure
- missing runnable work
- rejected runnable selection
- missing runnable selection
