# Runtime Recovery Integration Contract v1

## Purpose

Package 145 defines the public integration contract between completed Runtime Recovery governance and future runtime consumers.

This contract is contract-only. It defines integration requests, integration responses, consumer roles, compatibility rules, and authority requirements. It does not implement integration behavior.

Runtime Recovery integration may prepare requests, responses, and consumer-role declarations, but it MUST NOT authorize execution.

Execution may only be authorized by a future Runtime Recovery Execution Authority package.

## Public Contract Surface

Runtime Recovery Integration v1 defines two public contract identifiers:

| Contract | Identifier | Purpose |
| --- | --- | --- |
| Integration Request | `aer.runtime.recovery.integration_request.v1` | Describes a future consumer's request to consume a public Recovery Plan or Recovery integration intent. |
| Integration Response | `aer.runtime.recovery.integration_response.v1` | Describes whether the request is contract-compatible and which capabilities remain denied. |

The contract surface is descriptive only. A compatible response means the request may be understood by future packages. It does not mean recovery may run.

## Integration Request Schema

An Integration Request is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.integration_request.v1`. |
| `request_id` | string | Yes | Stable caller-provided identifier for the descriptive request. |
| `consumer_role` | string | Yes | One allowed consumer role from this contract. |
| `recovery_plan_contract` | string | Yes | Expected public Recovery Plan contract, normally `aer.runtime.recovery.plan.v1`. |
| `recovery_token` | string or null | Yes | Public Recovery Plan token when available. |
| `requested_boundary` | string | Yes | Requested integration boundary, such as `descriptive_recovery_integration_only`. |
| `intent` | string | Yes | Descriptive integration intent. |
| `metadata` | mapping | Yes | Caller metadata for future contract consumers. |
| `descriptive_only` | boolean | Yes | Must be `true`. |

Allowed `requested_boundary` values:

- `descriptive_recovery_integration_only`
- `contract_readiness_review`
- `future_authority_review`

No request field grants authority to schedule, dispatch, operate, persist, audit, journal, replay, mutate runtime state, or perform runtime work.

## Integration Response Schema

An Integration Response is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.integration_response.v1`. |
| `request_id` | string or null | Yes | Mirrors the request identifier when available. |
| `accepted` | boolean | Yes | Indicates whether the request is contract-compatible. |
| `status` | string | Yes | Response status from this contract's taxonomy. |
| `reason` | string or null | Yes | Human-readable explanation for incompatible or blocked requests. |
| `consumer_role` | string or null | Yes | Mirrors the requested consumer role when available. |
| `allowed_boundary` | string or null | Yes | Descriptive boundary granted to compatible requests. |
| `denied_capabilities` | list of strings | Yes | Capabilities denied by this contract. |
| `execution_authority_required` | boolean | Yes | Must be `true` for every response. |
| `execution_authorized` | boolean | Yes | Must be `false` for every response. |
| `descriptive_only` | boolean | Yes | Must be `true`. |

Allowed response statuses:

- `accepted_descriptive_only`
- `invalid_request_contract`
- `unknown_consumer_role`
- `forbidden_consumer_role`
- `invalid_recovery_plan_contract`
- `invalid_requested_boundary`
- `execution_authority_required`
- `integration_not_authorized`

The response may confirm contract compatibility. It must never authorize execution.

## Allowed Consumer Roles

Allowed consumer roles are descriptive or contract-facing only:

| Role | Allowed Use | Execution Authority |
| --- | --- | --- |
| `runtime_recovery_integration_contract` | Read and validate this public integration contract. | None |
| `runtime_recovery_integration_blueprint` | Review alignment with Package 144. | None |
| `runtime_recovery_execution_authority_candidate` | Prepare a future authority package contract review. | None |
| `scheduler_contract_candidate` | Prepare a future Scheduler-facing contract. | None |
| `dispatcher_contract_candidate` | Prepare a future Dispatcher-facing contract. | None |
| `operator_contract_candidate` | Prepare a future Operator-facing contract. | None |
| `persistence_contract_candidate` | Prepare future Persistence contract alignment. | None |
| `audit_contract_candidate` | Prepare future Audit contract alignment. | None |
| `journal_contract_candidate` | Prepare future Journal contract alignment. | None |
| `replay_contract_candidate` | Prepare future Replay contract alignment. | None |

Allowed roles may inspect public Recovery contract data and integration intent only. They may not perform downstream work.

## Forbidden Consumer Roles

Forbidden consumer roles include any consumer that claims direct execution authority:

- `scheduler_executor`
- `dispatcher_executor`
- `operator_executor`
- `task_runner_executor`
- `runtime_execution_loop`
- `persistence_writer`
- `audit_emitter`
- `journal_emitter`
- `replay_executor`
- `runtime_mutator`
- `file_mutator`
- `external_process_caller`

A request from a forbidden consumer role must receive a response with `accepted` set to `false`, `execution_authorized` set to `false`, and `execution_authority_required` set to `true`.

## Boundary Rules

Runtime Recovery Integration v1 follows these boundary rules:

- Requests and responses are public contract data only.
- Every request and response must remain descriptive only.
- A compatible request may prepare a future contract review.
- A compatible response may acknowledge only contract readability and role compatibility.
- Consumer-boundary acceptance does not become execution authority.
- Integration Contract acceptance does not become execution authority.
- Recovery Plans remain governed by their Recovery Execution Boundary.
- Recovery integration must not bypass Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, Replay, or Runtime execution lifecycle gates.

## Execution Authority Requirement

Execution authority is absent from this contract.

This contract may define integration requests, responses, and consumer roles, but it MUST NOT authorize execution.

Execution may only be authorized by a future Runtime Recovery Execution Authority package.

Until that future package exists, every Integration Response must set:

- `execution_authority_required` to `true`
- `execution_authorized` to `false`
- `descriptive_only` to `true`

## Prohibited Direct Integrations

Runtime Recovery Integration v1 prohibits direct integration with:

- Scheduler admission or scheduling paths
- Dispatcher command paths
- Operator action paths
- TaskRunner paths
- runtime execution loops
- persistence write paths
- audit emission paths
- journal emission paths
- replay action paths
- subprocess paths
- file IO paths
- runtime mutation paths
- runtime execution modules

Future packages must add their own public contracts and authority gates before any of these paths can consume Recovery integration output.

## Failure Taxonomy

Integration responses use this failure taxonomy:

| Status | Meaning | Execution Authority |
| --- | --- | --- |
| `invalid_request_contract` | Request shape or contract identifier is invalid. | Not granted |
| `unknown_consumer_role` | Consumer role is not known to this contract. | Not granted |
| `forbidden_consumer_role` | Consumer role is explicitly denied. | Not granted |
| `invalid_recovery_plan_contract` | Referenced Recovery Plan contract is missing or incompatible. | Not granted |
| `invalid_requested_boundary` | Requested boundary is not allowed. | Not granted |
| `execution_authority_required` | Request needs a future authority package before it can proceed. | Not granted |
| `integration_not_authorized` | Request is outside the contract boundary. | Not granted |

The only success status is `accepted_descriptive_only`, and it also grants no execution authority.

## Dependency Rules

Runtime Recovery Integration v1 may depend only on public Recovery governance contracts and documents:

```text
Runtime Recovery Closure Review
  -> Runtime Recovery Integration Blueprint
  -> Runtime Recovery Integration Contract v1
```

Allowed public Recovery references:

- `aer.runtime.recovery.eligibility.v1`
- `aer.runtime.recovery.plan.v1`
- `aer.runtime.recovery.execution_boundary.v1`
- `aer.runtime.recovery.consumer_boundary.v1`
- `aer.runtime.recovery.integration_request.v1`
- `aer.runtime.recovery.integration_response.v1`

Forbidden dependencies:

- Scheduler internals
- Dispatcher internals
- Operator internals
- Persistence internals
- Audit internals
- Journal internals
- Replay internals
- TaskRunner internals
- Runtime execution loops
- Runtime mutation modules
- subprocess helpers
- file IO helpers

## Compatibility Policy

Runtime Recovery Integration v1 is compatible only with descriptive Recovery surfaces that preserve execution denial:

| Upstream Surface | Compatible Version | Requirement |
| --- | --- | --- |
| Recovery Eligibility | `aer.runtime.recovery.eligibility.v1` | Must remain descriptive only. |
| Recovery Plan | `aer.runtime.recovery.plan.v1` | Must include an execution boundary that denies execution. |
| Recovery Execution Boundary | `aer.runtime.recovery.execution_boundary.v1` | Must deny execution and downstream authorization. |
| Recovery Consumer Boundary | `aer.runtime.recovery.consumer_boundary.v1` | Must deny scheduler, dispatcher, operator, persistence, audit, journal, replay, runtime mutation, file mutation, and external process capabilities. |

Consumers that require execution authority are not compatible with this contract until a future Runtime Recovery Execution Authority package exists.

## Contract Evolution Policy

Runtime Recovery Integration v1 is stable for the Package 145 boundary.

Breaking changes require a new contract version. Breaking changes include:

- renaming request or response fields
- removing required fields
- changing allowed consumer-role meanings
- changing forbidden consumer-role meanings
- changing denied capabilities into allowed capabilities
- allowing execution authority from this contract
- replacing descriptive-only semantics with runtime behavior

Non-breaking changes may add clarifying prose or new future-role recommendations only when existing v1 request and response meanings remain unchanged.

## GO / NO-GO Decision

Final decision: GO.

Runtime Recovery Integration Contract v1 is complete as a contract-only package.

The contract defines public integration request and response surfaces, allowed and forbidden consumer roles, boundary rules, dependency rules, compatibility policy, and evolution policy.

The contract does not authorize recovery execution or any direct Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, Replay, subprocess, file IO, runtime mutation, or runtime execution integration.

## Next Package Recommendation

Next package: Package 146.

Package 146 should define the Runtime Recovery Execution Authority package before any future runtime consumer can treat Recovery integration output as executable authority.
