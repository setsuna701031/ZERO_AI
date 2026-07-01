# Runtime Recovery Execution Authority Contract v1

## Purpose

Package 146 defines the single execution-authority layer for Runtime Recovery.

This authority contract establishes who may authorize Recovery execution and how an authorization decision is represented as public contract data.

Execution Authority MAY authorize.

Execution Authority MUST NOT execute.

Execution remains outside this package. This package does not invoke Scheduler, Dispatcher, Operator runtime, runtime supervisor, recovery executor, persistence, replay, audit, journal, subprocess, file IO, or runtime execution modules.

## Authority Ownership

Runtime Recovery Execution Authority is owned by the Runtime Recovery Execution Authority domain.

This domain owns only authorization decisions. It does not own Recovery execution, Scheduler admission, Dispatcher command, Operator action, runtime supervision, persistence, audit, journal, replay, or runtime mutation.

Authority ownership means:

- defining who may request Recovery execution authorization
- defining who may issue a Recovery execution authorization decision
- recording the decision as public contract data
- preserving downstream lifecycle gates
- denying unauthorized or incompatible authority requests

Authority ownership does not mean:

- executing Recovery
- invoking downstream runtime consumers
- creating runtime work
- persisting state
- emitting audit or journal records
- replaying Recovery
- mutating runtime state

## Public Authority Surface

Runtime Recovery Execution Authority v1 defines two public contract identifiers:

| Contract | Identifier | Purpose |
| --- | --- | --- |
| Authority Request | `aer.runtime.recovery.execution_authority_request.v1` | Requests an authority decision for a public Recovery integration response or Recovery Plan. |
| Authority Response | `aer.runtime.recovery.execution_authority_response.v1` | Records whether Recovery execution is authorized, denied, or blocked. |

The public authority surface may authorize Recovery execution as a decision only. It does not perform that execution or call any runtime consumer.

## Authority Request Schema

An Authority Request is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.execution_authority_request.v1`. |
| `authority_request_id` | string | Yes | Stable caller-provided identifier for the authority request. |
| `requesting_owner` | string | Yes | Owner requesting an authority decision. |
| `authority_owner` | string | Yes | Owner expected to make the authority decision. |
| `recovery_token` | string or null | Yes | Public Recovery Plan token when available. |
| `integration_response_contract` | string | Yes | Expected integration response contract, normally `aer.runtime.recovery.integration_response.v1`. |
| `requested_decision` | string | Yes | Requested authority decision, such as `authorize_recovery_execution`. |
| `reason` | string or null | Yes | Human-readable reason for the authority request. |
| `metadata` | mapping | Yes | Caller metadata for future authority consumers. |
| `authority_only` | boolean | Yes | Must be `true`. |

Allowed `requested_decision` values:

- `authorize_recovery_execution`
- `deny_recovery_execution`
- `block_recovery_execution`
- `review_recovery_execution_authority`

The request schema may ask for authorization. It does not itself authorize or execute Recovery.

## Authority Response Schema

An Authority Response is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.execution_authority_response.v1`. |
| `authority_request_id` | string or null | Yes | Mirrors the request identifier when available. |
| `authority_owner` | string or null | Yes | Owner that made the authority decision. |
| `authorized` | boolean | Yes | Whether Recovery execution is authorized as a decision. |
| `decision` | string | Yes | Authority decision outcome. |
| `state` | string | Yes | Authority state after the decision. |
| `reason` | string or null | Yes | Human-readable reason for the decision. |
| `authorized_scope` | string or null | Yes | Scope of the authorization decision when authorized. |
| `downstream_requirements` | list of strings | Yes | Required downstream packages or contracts before execution can occur. |
| `denied_capabilities` | list of strings | Yes | Capabilities still denied by this authority package. |
| `executes_recovery` | boolean | Yes | Must be `false`. |
| `authority_only` | boolean | Yes | Must be `true`. |

`authorized` may be `true` only when the decision is `authorized_for_future_handoff`. Even then, `executes_recovery` must remain `false`.

## Authority Decision Model

The authority decision model separates authorization from execution.

Decision process:

1. Confirm the request uses `aer.runtime.recovery.execution_authority_request.v1`.
2. Confirm `authority_owner` is allowed.
3. Confirm `requesting_owner` is not forbidden.
4. Confirm the integration response contract is compatible with `aer.runtime.recovery.integration_response.v1`.
5. Decide one of the allowed authority outcomes.
6. Return an Authority Response that records the decision and preserves `executes_recovery: false`.

The decision model may produce authorization for a future handoff. It may not perform the handoff.

## Allowed Authority Owners

Allowed authority owners are narrow and explicit:

| Owner | Authority Scope | Execution Permission |
| --- | --- | --- |
| `runtime_recovery_execution_authority` | May issue Recovery execution authority decisions. | None |
| `runtime_recovery_governance_authority` | May deny or block authority requests during governance review. | None |
| `runtime_recovery_authority_review` | May review authority readiness and recommend denial or block. | None |

Only `runtime_recovery_execution_authority` may produce `authorized_for_future_handoff`.

No allowed owner may execute Recovery from this package.

## Forbidden Authority Owners

Forbidden authority owners include any downstream runtime consumer or execution path:

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

A forbidden authority owner must receive a denied or blocked response. It must not receive authorization from this contract.

## Authority State Model

Authority state is represented only in Authority Response data:

| State | Meaning | Execution Behavior |
| --- | --- | --- |
| `requested` | Authority request was received by a future validator or reviewer. | None |
| `authorized` | Authority decision allows future handoff after downstream gates. | None |
| `denied` | Authority decision rejects the request. | None |
| `blocked` | Authority decision cannot proceed because required contract gates are missing. | None |
| `invalid` | Authority request is structurally invalid. | None |

Authority state does not persist runtime state and does not mutate Recovery state.

## Decision Outcomes

Allowed decision outcomes:

| Decision | `authorized` | Meaning |
| --- | --- | --- |
| `authorized_for_future_handoff` | `true` | Recovery execution is authorized as a decision, but execution still requires separate downstream integration packages. |
| `denied_by_authority` | `false` | Authority owner denied Recovery execution authorization. |
| `blocked_missing_downstream_contract` | `false` | Required Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, Replay, or runtime execution contracts are missing. |
| `blocked_forbidden_owner` | `false` | Request used a forbidden authority owner or requesting owner. |
| `invalid_authority_request` | `false` | Request shape, contract identifier, or required field is invalid. |
| `incompatible_integration_contract` | `false` | Integration response contract is not compatible. |

Even `authorized_for_future_handoff` does not execute Recovery.

## Failure Taxonomy

Authority responses use this failure taxonomy:

| Failure | Meaning | Recovery Execution |
| --- | --- | --- |
| `invalid_authority_request` | Authority request cannot be understood. | Not performed |
| `unknown_authority_owner` | Authority owner is not recognized. | Not performed |
| `forbidden_authority_owner` | Authority owner is explicitly denied. | Not performed |
| `forbidden_requesting_owner` | Requesting owner is explicitly denied. | Not performed |
| `incompatible_integration_contract` | Integration response contract is missing or incompatible. | Not performed |
| `missing_downstream_contract` | Required downstream contract gate is absent. | Not performed |
| `authority_denied` | Authority owner denied the request. | Not performed |

Failures are data-only decision outcomes.

## Boundary Rules

Runtime Recovery Execution Authority v1 follows these boundary rules:

- The package may authorize Recovery execution as a public decision.
- The package must not execute Recovery.
- The package must not invoke Scheduler, Dispatcher, Operator runtime, runtime supervisor, recovery executor, persistence, replay, audit, journal, subprocess, file IO, or runtime execution modules.
- Authorization does not bypass downstream domain lifecycle gates.
- Authorization does not create Scheduler admission.
- Authorization does not create Dispatcher command.
- Authorization does not create Operator action.
- Authorization does not create persistence, audit, journal, replay, or runtime mutation.
- Authorization may be consumed only by future packages that explicitly define their own contract and behavior.

## Dependency Rules

Runtime Recovery Execution Authority v1 may depend only on public Recovery governance and integration contracts:

```text
Runtime Recovery Closure Review
  -> Runtime Recovery Integration Blueprint
  -> Runtime Recovery Integration Contract v1
  -> Runtime Recovery Execution Authority Contract v1
```

Allowed public references:

- `aer.runtime.recovery.integration_request.v1`
- `aer.runtime.recovery.integration_response.v1`
- `aer.runtime.recovery.execution_authority_request.v1`
- `aer.runtime.recovery.execution_authority_response.v1`
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

## Compatibility Policy

Runtime Recovery Execution Authority v1 is compatible only with public integration responses and Recovery Plans that preserve explicit separation between authorization and execution.

| Upstream Surface | Compatible Version | Requirement |
| --- | --- | --- |
| Recovery Integration Response | `aer.runtime.recovery.integration_response.v1` | Must identify that authority is required and must not execute Recovery. |
| Recovery Plan | `aer.runtime.recovery.plan.v1` | Must include a public execution boundary. |
| Recovery Execution Boundary | `aer.runtime.recovery.execution_boundary.v1` | Must be available for authority review. |

Downstream consumers remain incompatible until they define their own public contract and lifecycle gate.

## Authority Evolution Policy

Runtime Recovery Execution Authority v1 is stable for the Package 146 boundary.

Breaking changes require a new authority contract version. Breaking changes include:

- changing request or response field names
- removing required request or response fields
- changing allowed authority owner meanings
- changing forbidden authority owner meanings
- allowing this package to execute Recovery
- allowing this package to invoke downstream runtime consumers
- replacing authority-only semantics with runtime behavior

Non-breaking changes may add clarifying prose, additional denied capabilities, or future downstream compatibility notes when v1 request and response meanings remain unchanged.

## GO / NO-GO

Final decision: GO.

Runtime Recovery Execution Authority Contract v1 is complete as an authority-only package.

The contract defines who may authorize Recovery execution and how that decision is represented.

Execution Authority MAY authorize.

Execution Authority MUST NOT execute.

Execution remains outside this package.

## Next Package

Next package: Package 147.

Package 147 should define the next downstream Recovery integration contract after authority is sealed, without implementing runtime execution.
