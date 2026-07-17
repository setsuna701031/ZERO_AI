# Runtime Recovery Activation Contract v1

## Purpose

Package 156 defines the passive Runtime Recovery Activation request and response contract.

This contract prepares activation data only. It does not activate Recovery, schedule work, dispatch commands, invoke Operator runtime, supervise runtime work, call Native Runtime, persist, replay, audit, journal, perform file IO, call subprocess, or mutate runtime state.

## Activation Request Schema

An Activation Request is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.activation_request.v1`. |
| `activation_id` | string or null | Yes | Stable caller-provided activation identifier. |
| `requested_state` | string | Yes | Requested activation preparation state. |
| `integration_report_reference` | mapping | Yes | Data-only reference to Package 152 runtime integration report. |
| `authority_reference` | mapping | Yes | Data-only authority response reference. |
| `intent_reference` | mapping | Yes | Data-only intent response reference. |
| `bridge_reference` | mapping | Yes | Data-only bridge response reference. |
| `executor_report_reference` | mapping | Yes | Data-only executor report reference. |
| `metadata` | mapping | Yes | Caller metadata for future activation consumers. |
| `activation_only` | boolean | Yes | Must be `true`. |

## Activation Response Schema

An Activation Response is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.activation_response.v1`. |
| `activation_id` | string or null | Yes | Mirrors the request identifier when available. |
| `prepared` | boolean | Yes | Whether activation data is prepared for a future hook package. |
| `blocked` | boolean | Yes | Whether activation preparation is blocked by invalid passive references. |
| `denied` | boolean | Yes | Whether activation preparation is denied by a forbidden state. |
| `activation_state` | string | Yes | One of the allowed activation states. |
| `integration_report_reference` | mapping | Yes | Copied data-only runtime integration report reference. |
| `authority_reference` | mapping | Yes | Copied data-only authority response reference. |
| `intent_reference` | mapping | Yes | Copied data-only intent response reference. |
| `bridge_reference` | mapping | Yes | Copied data-only bridge response reference. |
| `executor_report_reference` | mapping | Yes | Copied data-only executor report reference. |
| `denied_runtime_hooks` | list of strings | Yes | Runtime hooks still denied by this contract. |
| `reason` | string or null | Yes | Human-readable preparation reason. |
| `metadata` | mapping | Yes | Caller metadata copied as plain data. |
| `activation_only` | boolean | Yes | Must be `true`. |
| `executes_recovery` | boolean | Yes | Must be `false`. |
| `side_effects_performed` | boolean | Yes | Must be `false`. |
| `plain_dict_only` | boolean | Yes | Must be `true`. |

Activation response preparation does not authorize runtime execution.

## Required Authority Reference

Every Activation Request must include a data-only reference to `aer.runtime.recovery.execution_authority_response.v1`.

The authority reference must preserve authority-only semantics, `authorized_for_future_handoff`, and `executes_recovery: false`.

## Required Intent Reference

Every Activation Request must include a data-only reference to `aer.runtime.recovery.execution_intent_response.v1`.

The intent reference must preserve intent-only semantics, descriptive actions only, and `executes_recovery: false`.

## Required Bridge Reference

Every Activation Request must include a data-only reference to `aer.runtime.recovery.runtime_bridge_response.v1`.

The bridge reference must preserve bridge-only semantics, accepted passive bridge data, and `executes_recovery: false`.

## Required Executor Report Reference

Every Activation Request must include a data-only reference to `aer.runtime.recovery.executor_report.v1`.

The executor report reference must preserve side-effect-free executor preparation, `prepared_no_side_effects`, and `executes_recovery: false`.

## Allowed Activation States

Allowed activation states are passive preparation states:

- `prepared`
- `blocked`
- `denied`

Allowed states do not schedule, dispatch, operate, supervise, execute, persist, replay, audit, journal, perform file IO, call subprocess, or mutate runtime state.

## Forbidden Activation States

Forbidden activation states are runtime behavior states:

- `activated`
- `activating`
- `running`
- `scheduled`
- `dispatched`
- `operator_started`
- `supervised`
- `executed`
- `persisted`
- `replayed`
- `audited`
- `journaled`
- `mutated`

A forbidden activation state must produce a denied activation response.

## Activation Boundary Rules

Runtime Recovery Activation v1 follows these boundary rules:

- Activation may prepare deterministic passive activation data.
- Activation may validate authority, intent, bridge, and executor report references.
- Activation may mark preparation as prepared, blocked, or denied.
- Activation must not create Scheduler admissions.
- Activation must not dispatch runtime commands.
- Activation must not request or apply Operator actions.
- Activation must not supervise runtime sessions.
- Activation must not call Native Runtime execution.
- Activation must not persist, replay, audit, journal, perform file IO, call subprocess, or mutate runtime state.

## Prohibited Direct Runtime Hooks

This contract prohibits direct hooks to:

- Scheduler admission or scheduling paths
- Dispatcher command paths
- Operator runtime action paths
- Runtime Supervisor paths
- Native Runtime execution paths
- persistence write paths
- replay action paths
- audit emission paths
- journal emission paths
- subprocess paths
- file IO paths
- runtime mutation paths

## Compatibility Policy

Runtime Recovery Activation v1 is compatible only with passive Package 152 integration reports that preserve Package 146 authority, Package 147 intent, Package 149 bridge, and Package 151 executor report references.

Breaking changes require a new activation contract version. Breaking changes include changing request or response field names, removing required references, allowing forbidden activation states, or allowing direct runtime hooks.

Non-breaking changes may add clarifying prose, denied hook names, or downstream readiness notes when v1 field meanings remain unchanged.

## GO / NO-GO

Final decision: GO.

Runtime Recovery Activation Contract v1 is complete as a contract-only package.

## Next Package

Next package: Package 157.
