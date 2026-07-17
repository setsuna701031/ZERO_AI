# Runtime Controlled Executor Activation v1

## Purpose

This contract defines the controlled path from executor handoff readiness into executor activation data handling.

The bundle does not grant uncontrolled execution. It creates deterministic records for activation admission, an injected activation bridge, and activation result intake.

## Inputs

### RuntimeExecutorHandoffRecord

Required fields:

- `executor_handoff_authorized`
- `handoff_work_id`
- `source_selection_id`
- `executor_called`
- `execution_started`
- `runtime_state_mutated`

## Outputs

### RuntimeExecutorActivationAdmissionRecord

Required fields:

- `executor_activation_admitted`
- `source_handoff_id`
- `handoff_work_id`
- `activation_reason`
- `denial_reason`
- `executor_called`
- `execution_started`
- `runtime_state_mutated`

### RuntimeExecutorActivationBridgeRecord

Required fields:

- `executor_activation_bridge_authorized`
- `source_activation_admission_id`
- `handoff_work_id`
- `activation_handler_called`
- `activation_result_received`
- `activation_result`
- `execution_started`
- `runtime_state_mutated`
- `denial_reason`

### RuntimeExecutorResultIntakeRecord

Required fields:

- `executor_result_intake_authorized`
- `source_activation_bridge_id`
- `handoff_work_id`
- `result_accepted`
- `terminal_status`
- `denial_reason`
- `execution_started`
- `runtime_state_mutated`

## Rules

- Activation admission requires a valid executor handoff record.
- Activation bridge may call only an injected handler.
- Activation bridge payload is limited to `handoff_work_id` and `source_activation_admission_id`.
- Result intake only accepts activation handler data.
- No layer starts execution.
- No layer mutates runtime state.
- No layer updates progress memory or cursor state.

## Final Decision

GO for controlled executor activation data path only.
