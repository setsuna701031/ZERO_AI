# Runtime Recovery Kill Switch Contract v1

## Purpose

Package 168 defines passive Runtime Recovery kill-switch semantics.

The kill switch defaults to disabled, off, and safe.

This contract does not execute Recovery, enable Recovery by default, perform recovery actions, mutate runtime state, persist, replay, audit, journal, call subprocess, perform file IO, or call Scheduler, Operator, Dispatcher, Runtime Supervisor, or Native Runtime behavior.

## Required Input

The kill switch may consume only `aer.runtime.recovery.controlled_activation_report.v1`.

The controlled activation report must keep:

- activation gate OFF
- activation not allowed
- runtime mainline wiring not allowed
- preparation-only semantics
- no Recovery execution
- no side effects

## Kill Switch Report

A kill-switch report is plain data containing:

- `contract`
- `kill_switch_id`
- `prepared`
- `blocked`
- `denied`
- `status`
- `kill_switch_enabled`
- `kill_switch_state`
- `safe_mode`
- `recovery_enabled`
- `controlled_activation_reference`
- `denied_capabilities`
- `reason`
- `metadata`
- `kill_switch_only`
- `executes_recovery`
- `side_effects_performed`
- `plain_dict_only`

## Default Safe Rule

Default kill-switch reports must set:

- `kill_switch_enabled` to `false`
- `kill_switch_state` to `off`
- `safe_mode` to `true`
- `recovery_enabled` to `false`
- `executes_recovery` to `false`
- `side_effects_performed` to `false`

## Allowed States

Allowed passive states:

- `prepared`
- `blocked`
- `denied`

## Denied Capabilities

The kill switch denies:

- Recovery enablement
- Recovery execution
- runtime mainline wiring
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

Runtime Recovery Kill Switch Contract v1 is complete as a passive kill-switch contract.

## Next Package

Next package: Package 169.
