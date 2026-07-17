# Controlled Activation Switch Dry Run v1 Contract

Package range: 1121-1128.

Status: disabled / dry-run-only / preview-only.

## Purpose

This contract reserves the dry-run transaction surface for controlled runtime activation.

It simulates a transition from disabled or preview-only mode into a controlled active candidate mode without changing runtime mode or enabling any real execution authority.

## Required fields

- `activation_attempt_id`
- `transition_id`
- `request_id`
- `operator_id`
- `previous_mode`
- `target_mode`
- `readiness_result`
- `rollback_plan`
- `emergency_disable_plan`
- `audit_required`

## Required dry-run paths

- transition simulation
- rollback simulation
- emergency disable simulation
- activation state projection
- activation audit trail

## Mandatory disabled outputs

Every dry-run result must keep:

- `enabled: false`
- `dry_run_only: true`
- `preview_only: true`
- `controlled_activation_allowed: false`
- `runtime_mode_transition_performed: false`
- `controlled_active_enabled: false`
- `real_mutation_enabled: false`
- `real_tool_execution_enabled: false`
- `autonomous_execution_enabled: false`
- `new_task_dispatched: false`
- `tool_invoked: false`
- `external_io_performed: false`

## Non-mainline issue reporting rule

Any issue discovered outside this package scope must be reported explicitly and must not be silently skipped, hidden, or bypassed.
