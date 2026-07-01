# Runtime Recovery Wiring Gate Contract v1

## Purpose

Package 164 defines the passive Recovery Wiring Gate contract.

The gate evaluates whether the passive Scheduler, Operator, Runtime Supervisor, and Native Runtime adapter reports are coherent enough for controlled activation preparation.

The activation gate is OFF by default.

This contract does not activate Recovery, wire Recovery into runtime mainline, call Scheduler, call Operator, call Dispatcher, call Runtime Supervisor, call Native Runtime, mutate state, persist, replay, audit, journal, call subprocess, or perform file IO.

## Gate Input Schema

A gate input is plain data containing:

- Scheduler passive adapter report
- Operator passive adapter report
- Runtime Supervisor passive adapter report
- Native Runtime passive adapter report
- requested gate state
- metadata

## Gate Report Schema

A gate report is a plain mapping containing:

- `contract`
- `gate_id`
- `prepared`
- `blocked`
- `denied`
- `status`
- `activation_gate_enabled`
- `activation_allowed`
- `wiring_allowed`
- `scheduler_adapter_reference`
- `operator_adapter_reference`
- `supervisor_adapter_reference`
- `native_adapter_reference`
- `denied_capabilities`
- `reason`
- `metadata`
- `gate_only`
- `executes_recovery`
- `side_effects_performed`
- `plain_dict_only`

## Allowed Gate States

Allowed passive gate states:

- `prepared`
- `blocked`
- `denied`

## Default Gate Rule

The activation gate must remain OFF by default.

Default gate reports must set:

- `activation_gate_enabled` to `false`
- `activation_allowed` to `false`
- `wiring_allowed` to `false`
- `gate_only` to `true`
- `executes_recovery` to `false`
- `side_effects_performed` to `false`

## Required Adapter References

The gate must preserve these references when valid:

- `aer.runtime.recovery.scheduler_adapter_report.v1`
- `aer.runtime.recovery.operator_adapter_report.v1`
- `aer.runtime.recovery.supervisor_adapter_report.v1`
- `aer.runtime.recovery.native_adapter_report.v1`

Each adapter reference must remain prepared, adapter-only, plain dict data.

## Denied Runtime Capabilities

The gate denies:

- scheduler calls
- operator calls
- dispatcher calls
- supervisor calls
- native runtime calls
- runtime mutation
- persistence writes
- replay actions
- audit emissions
- journal events
- subprocess calls
- file IO

## GO / NO-GO

Final decision: GO.

Recovery Wiring Gate Contract v1 is complete as a passive gate contract.

## Next Package

Next package: Package 165.
