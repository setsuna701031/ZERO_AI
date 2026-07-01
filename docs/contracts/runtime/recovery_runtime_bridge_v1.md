# Runtime Recovery Runtime Bridge Contract v1

## Purpose

Package 148 defines the public bridge contract from Recovery governance and Execution Intent into a future runtime bridge.

The Runtime Recovery Runtime Bridge Contract describes how authorized Recovery intent may be represented for a future bridge package.

This contract is contract-only. It MUST NOT execute recovery, invoke Scheduler, invoke Dispatcher, invoke Operator runtime, invoke runtime supervisor, persist, replay, audit, journal, mutate runtime state, perform file IO, call subprocess, or call runtime execution modules.

## Public Bridge Surface

Runtime Recovery Runtime Bridge v1 defines two public contract identifiers:

| Contract | Identifier | Purpose |
| --- | --- | --- |
| Bridge Request | `aer.runtime.recovery.runtime_bridge_request.v1` | Requests a passive bridge report for an authorized Recovery Execution Intent. |
| Bridge Response | `aer.runtime.recovery.runtime_bridge_response.v1` | Records whether the bridge request is accepted as inert bridge data. |

The public bridge surface is passive data only.

## Bridge Request Schema

A Bridge Request is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.runtime_bridge_request.v1`. |
| `bridge_request_id` | string | Yes | Stable caller-provided bridge request identifier. |
| `bridge_consumer` | string | Yes | Consumer requesting bridge data. |
| `authority_reference` | mapping | Yes | Data-only reference to Package 146 authority response. |
| `intent_reference` | mapping | Yes | Data-only reference to Package 147 intent response. |
| `recovery_token` | string or null | Yes | Public Recovery Plan token when available. |
| `requested_bridge_scope` | string | Yes | Requested passive bridge scope. |
| `metadata` | mapping | Yes | Caller metadata for future bridge consumers. |
| `bridge_only` | boolean | Yes | Must be `true`. |

Allowed `requested_bridge_scope` values:

- `passive_recovery_runtime_bridge`
- `bridge_readiness_review`
- `future_executor_boundary_review`

## Bridge Response Schema

A Bridge Response is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.runtime_bridge_response.v1`. |
| `bridge_request_id` | string or null | Yes | Mirrors the request identifier when available. |
| `bridge_consumer` | string or null | Yes | Mirrors the bridge consumer when available. |
| `accepted` | boolean | Yes | Whether the bridge request is accepted as passive bridge data. |
| `status` | string | Yes | Bridge status from this contract's taxonomy. |
| `authority_reference` | mapping | Yes | Copied data-only authority reference. |
| `intent_reference` | mapping | Yes | Copied data-only intent reference. |
| `bridge_scope` | string or null | Yes | Passive bridge scope when accepted. |
| `denied_capabilities` | list of strings | Yes | Capabilities still denied by this bridge package. |
| `reason` | string or null | Yes | Human-readable response reason. |
| `executes_recovery` | boolean | Yes | Must be `false`. |
| `bridge_only` | boolean | Yes | Must be `true`. |

Bridge response acceptance does not authorize execution.

## Required Authority Reference

Every valid Bridge Request must include a data-only reference to:

- `aer.runtime.recovery.execution_authority_request.v1`
- `aer.runtime.recovery.execution_authority_response.v1`

The authority reference must identify a Package 146 authority decision compatible with `authorized_for_future_handoff`.

The bridge may reject or block requests when authority is missing, denied, invalid, or incompatible.

## Required Intent Reference

Every valid Bridge Request must include a data-only reference to:

- `aer.runtime.recovery.execution_intent_request.v1`
- `aer.runtime.recovery.execution_intent_response.v1`

The intent reference must preserve `intent_only: true`, `executes_recovery: false`, and descriptive intended actions only.

The bridge may reject or block requests when intent is missing, denied, invalid, incompatible, or contains forbidden runtime behavior.

## Allowed Bridge Consumers

Allowed bridge consumers are passive contract consumers:

| Consumer | Allowed Use | Runtime Permission |
| --- | --- | --- |
| `runtime_recovery_runtime_bridge` | Build or validate passive bridge data. | None |
| `runtime_recovery_executor_boundary` | Review future executor boundary inputs. | None |
| `runtime_recovery_bridge_review` | Review bridge compatibility and readiness. | None |

Allowed consumers may inspect public authority and intent data only.

## Forbidden Bridge Consumers

Forbidden bridge consumers include direct runtime consumers:

- `scheduler`
- `dispatcher`
- `operator_runtime`
- `runtime_supervisor`
- `recovery_executor`
- `task_runner`
- `persistence`
- `audit`
- `journal`
- `replay`
- `runtime_execution_loop`
- `runtime_mutation_module`
- `file_io_owner`
- `subprocess_owner`

A forbidden bridge consumer must receive an unaccepted bridge response.

## Boundary Rules

Runtime Recovery Runtime Bridge v1 follows these boundary rules:

- The bridge may describe passive bridge readiness.
- The bridge must not execute Recovery.
- The bridge must not schedule, dispatch, operate, supervise, persist, replay, audit, journal, mutate, perform file IO, call subprocess, or call runtime modules.
- The bridge does not create runtime work.
- The bridge does not bypass Package 146 authority, Package 147 intent, or future executor boundaries.
- The bridge may be consumed only by future packages that define their own public contract and behavior.

## Dependency Rules

Runtime Recovery Runtime Bridge v1 may depend only on public Recovery governance, integration, authority, and intent contracts:

```text
Runtime Recovery Integration Contract v1
  -> Runtime Recovery Execution Authority Contract v1
  -> Runtime Recovery Execution Intent Contract v1
  -> Runtime Recovery Runtime Bridge Contract v1
```

Allowed public references:

- `aer.runtime.recovery.integration_response.v1`
- `aer.runtime.recovery.execution_authority_response.v1`
- `aer.runtime.recovery.execution_intent_response.v1`
- `aer.runtime.recovery.runtime_bridge_request.v1`
- `aer.runtime.recovery.runtime_bridge_response.v1`
- `aer.runtime.recovery.plan.v1`
- `aer.runtime.recovery.execution_boundary.v1`

Forbidden dependencies:

- Scheduler internals
- Dispatcher internals
- Operator runtime internals
- Runtime supervisor internals
- Recovery executor internals
- Persistence internals
- Audit internals
- Journal internals
- Replay internals
- TaskRunner internals
- file IO helpers
- subprocess helpers
- runtime execution modules

## Prohibited Runtime Calls

This contract prohibits calls to:

- Scheduler admission or scheduling paths
- Dispatcher command paths
- Operator runtime action paths
- runtime supervisor paths
- recovery executor paths
- TaskRunner paths
- persistence write paths
- replay action paths
- audit emission paths
- journal emission paths
- runtime mutation paths
- file IO paths
- subprocess paths
- runtime execution modules

## Compatibility Policy

Runtime Recovery Runtime Bridge v1 is compatible only with public authority and intent surfaces that preserve execution denial.

| Upstream Surface | Compatible Version | Requirement |
| --- | --- | --- |
| Recovery Execution Authority Response | `aer.runtime.recovery.execution_authority_response.v1` | Must preserve authority-only semantics and `executes_recovery: false`. |
| Recovery Execution Intent Response | `aer.runtime.recovery.execution_intent_response.v1` | Must preserve intent-only semantics and descriptive actions only. |
| Recovery Plan | `aer.runtime.recovery.plan.v1` | Must include a public execution boundary. |

Downstream executor consumers remain incompatible until an executor boundary contract exists.

## Evolution Policy

Runtime Recovery Runtime Bridge v1 is stable for the Package 148 boundary.

Breaking changes require a new bridge contract version. Breaking changes include:

- changing request or response field names
- removing required request or response fields
- changing allowed bridge consumer meanings
- changing forbidden bridge consumer meanings
- allowing this package to execute Recovery
- allowing this package to call runtime modules
- replacing bridge-only semantics with runtime behavior

Non-breaking changes may add clarifying prose, denied capabilities, or future downstream compatibility notes when v1 request and response meanings remain unchanged.

## GO / NO-GO

Final decision: GO.

Runtime Recovery Runtime Bridge Contract v1 is complete as a contract-only package.

The bridge contract defines passive bridge data from authority and intent into a future runtime bridge.

It does not execute Recovery or invoke runtime behavior.

## Next Package

Next package: Package 149.

Package 149 should create a passive bridge helper that produces stable bridge reports without executing Recovery.
