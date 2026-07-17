# Runtime Recovery Execution Intent Contract v1

## Purpose

Package 147 defines the Recovery Execution Intent layer.

This contract describes what an authorized Recovery execution would intend to do if a future downstream execution package consumes a valid authority decision.

Execution Intent MAY describe intended Recovery actions.

Execution Intent MUST NOT execute, schedule, dispatch, persist, replay, audit, journal, mutate runtime state, call runtime modules, perform file IO, call subprocess, or modify runtime execution modules.

Execution remains outside this package.

## Intent Ownership

Runtime Recovery Execution Intent is owned by the Runtime Recovery Execution Intent domain.

This domain owns only intent description. It does not own Recovery execution, Scheduler admission, Dispatcher command, Operator runtime action, runtime supervision, persistence, audit, journal, replay, recovery execution, runtime mutation, file IO, subprocess calls, or runtime execution module changes.

Intent ownership means:

- defining the public shape of an intent request
- defining the public shape of an intent response
- describing requested Recovery actions as inert contract data
- preserving the required authority reference from Package 146
- denying action requests that would cross into runtime behavior

Intent ownership does not mean:

- executing Recovery
- scheduling Recovery
- dispatching Recovery
- invoking Operator runtime behavior
- invoking runtime supervisor behavior
- invoking a recovery executor
- persisting Recovery state
- replaying Recovery
- emitting audit or journal records
- mutating runtime state
- calling runtime modules

## Public Intent Surface

Runtime Recovery Execution Intent v1 defines two public contract identifiers:

| Contract | Identifier | Purpose |
| --- | --- | --- |
| Intent Request | `aer.runtime.recovery.execution_intent_request.v1` | Describes proposed Recovery actions for a previously authorized authority decision. |
| Intent Response | `aer.runtime.recovery.execution_intent_response.v1` | Records whether proposed intent data is structurally accepted, denied, blocked, or invalid. |

The public intent surface is descriptive only. It may name intended actions, but it never performs those actions.

## Intent Request Schema

An Intent Request is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.execution_intent_request.v1`. |
| `intent_request_id` | string | Yes | Stable caller-provided identifier for the intent request. |
| `requesting_owner` | string | Yes | Owner requesting intent description. |
| `intent_owner` | string | Yes | Owner expected to describe Recovery execution intent. |
| `authority_response_contract` | string | Yes | Must reference `aer.runtime.recovery.execution_authority_response.v1`. |
| `authority_request_id` | string or null | Yes | Authority request identifier associated with the authorization decision when available. |
| `authority_decision` | string | Yes | Authority decision being referenced, normally `authorized_for_future_handoff`. |
| `recovery_token` | string or null | Yes | Public Recovery Plan token when available. |
| `integration_response_contract` | string | Yes | Expected integration response contract, normally `aer.runtime.recovery.integration_response.v1`. |
| `requested_actions` | list of strings | Yes | Proposed intent actions from the allowed intent action vocabulary. |
| `reason` | string or null | Yes | Human-readable reason for the intent request. |
| `metadata` | mapping | Yes | Caller metadata for future intent consumers. |
| `intent_only` | boolean | Yes | Must be `true`. |

The request schema may describe intended actions. It does not grant permission to run them.

## Intent Response Schema

An Intent Response is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.execution_intent_response.v1`. |
| `intent_request_id` | string or null | Yes | Mirrors the request identifier when available. |
| `intent_owner` | string or null | Yes | Owner that described or rejected the intent. |
| `authority_reference` | mapping | Yes | Data-only reference to the authority response and decision used by this intent. |
| `accepted` | boolean | Yes | Whether the requested intent is structurally accepted as descriptive data. |
| `status` | string | Yes | Intent response status from this contract's taxonomy. |
| `state` | string | Yes | Intent state after the response. |
| `intended_actions` | list of strings | Yes | Accepted descriptive actions, or an empty list when denied, blocked, or invalid. |
| `denied_actions` | list of strings | Yes | Requested actions rejected by this contract. |
| `denied_capabilities` | list of strings | Yes | Capabilities still denied by this intent package. |
| `reason` | string or null | Yes | Human-readable reason for the response. |
| `executes_recovery` | boolean | Yes | Must be `false`. |
| `intent_only` | boolean | Yes | Must be `true`. |

`accepted` may be `true` only for descriptive intent data. `executes_recovery` must remain `false`.

## Required Authority Reference

Every valid Intent Request must reference the Package 146 authority response contract:

- `aer.runtime.recovery.execution_authority_request.v1`
- `aer.runtime.recovery.execution_authority_response.v1`

The preferred authority decision for accepted intent is `authorized_for_future_handoff`.

Intent may be rejected or blocked when authority is denied, missing, incompatible, or not scoped to future handoff.

Authority reference is data-only. It does not trigger execution, handoff, Scheduler admission, Dispatcher command, Operator runtime action, runtime supervision, persistence, audit, journal, replay, runtime mutation, file IO, subprocess calls, or runtime module calls.

## Intent State Model

Intent state is represented only in Intent Response data:

| State | Meaning | Runtime Behavior |
| --- | --- | --- |
| `requested` | Intent request was received by a future validator or reviewer. | None |
| `described` | Intent actions were accepted as descriptive data. | None |
| `denied` | Intent actions were rejected by this contract. | None |
| `blocked` | Intent cannot be accepted because required authority or downstream gates are missing. | None |
| `invalid` | Intent request is structurally invalid. | None |

Intent state does not persist Recovery state and does not mutate runtime state.

## Intent Action Vocabulary

Intent action vocabulary is a controlled list of descriptive action names.

Action names describe future Recovery work at a contract level. They are not commands, callbacks, jobs, tasks, effects, or runtime instructions.

Allowed vocabulary entries must:

- be plain strings
- describe Recovery action intent
- depend on Package 146 authority by reference
- preserve `intent_only: true`
- preserve `executes_recovery: false`

## Allowed Intent Actions

Allowed intent actions are descriptive only:

| Action | Meaning | Runtime Behavior |
| --- | --- | --- |
| `describe_recovery_execution_intent` | Describe the overall intended Recovery execution path. | None |
| `describe_recovery_plan_handoff_intent` | Describe future handoff of a public Recovery Plan after authority gates. | None |
| `describe_scheduler_admission_intent` | Describe that a future Scheduler contract may need admission data. | None |
| `describe_dispatcher_command_intent` | Describe that a future Dispatcher contract may need command data. | None |
| `describe_operator_decision_intent` | Describe that a future Operator contract may need decision data. | None |
| `describe_persistence_alignment_intent` | Describe that a future Persistence contract may need alignment. | None |
| `describe_audit_alignment_intent` | Describe that a future Audit contract may need alignment. | None |
| `describe_journal_alignment_intent` | Describe that a future Journal contract may need alignment. | None |
| `describe_replay_alignment_intent` | Describe that a future Replay contract may need alignment. | None |
| `describe_runtime_supervision_intent` | Describe that a future runtime supervision contract may need alignment. | None |

These actions may be named in request or response data only.

## Forbidden Intent Actions

Forbidden intent actions include any direct runtime behavior:

- execute Recovery
- invoke Scheduler behavior
- invoke Dispatcher behavior
- invoke Operator runtime behavior
- invoke runtime supervisor behavior
- invoke recovery executor behavior
- create runtime work
- persist Recovery state
- replay Recovery
- emit audit records
- emit journal records
- mutate Recovery state
- mutate runtime state
- perform file IO
- call subprocess
- call runtime execution modules
- modify runtime execution modules

A request containing forbidden intent actions must receive `accepted: false`, an empty `intended_actions` list, and denied or blocked status.

## Boundary Rules

Runtime Recovery Execution Intent v1 follows these boundary rules:

- The package may describe intended Recovery actions.
- The package must not execute Recovery.
- The package must not invoke Scheduler, Dispatcher, Operator runtime, runtime supervisor, recovery executor, persistence, replay, audit, journal, subprocess, file IO, or runtime execution modules.
- Intent does not create Scheduler admission.
- Intent does not create Dispatcher command.
- Intent does not create Operator action.
- Intent does not create persistence, audit, journal, replay, runtime mutation, runtime work, or runtime supervision.
- Intent does not bypass Package 146 authority or future downstream lifecycle gates.
- Intent may be consumed only by future packages that explicitly define their own contract and behavior.

## Dependency Rules

Runtime Recovery Execution Intent v1 may depend only on public Recovery governance, integration, and authority contracts:

```text
Runtime Recovery Closure Review
  -> Runtime Recovery Integration Blueprint
  -> Runtime Recovery Integration Contract v1
  -> Runtime Recovery Execution Authority Contract v1
  -> Runtime Recovery Execution Intent Contract v1
```

Allowed public references:

- `aer.runtime.recovery.integration_request.v1`
- `aer.runtime.recovery.integration_response.v1`
- `aer.runtime.recovery.execution_authority_request.v1`
- `aer.runtime.recovery.execution_authority_response.v1`
- `aer.runtime.recovery.execution_intent_request.v1`
- `aer.runtime.recovery.execution_intent_response.v1`
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

## Failure Taxonomy

Intent responses use this failure taxonomy:

| Status | Meaning | Recovery Execution |
| --- | --- | --- |
| `accepted_intent_only` | Intent actions are accepted as descriptive data only. | Not performed |
| `invalid_intent_request` | Intent request cannot be understood. | Not performed |
| `missing_authority_reference` | Required authority response reference is absent. | Not performed |
| `incompatible_authority_reference` | Authority reference is not compatible with Package 146. | Not performed |
| `authority_not_authorized` | Referenced authority did not authorize future handoff. | Not performed |
| `unknown_intent_owner` | Intent owner is not recognized. | Not performed |
| `forbidden_intent_owner` | Intent owner is explicitly denied. | Not performed |
| `forbidden_intent_action` | Requested action crosses into runtime behavior. | Not performed |
| `missing_downstream_contract` | Required downstream contract gate is absent. | Not performed |

Failures are data-only outcomes.

## Compatibility Policy

Runtime Recovery Execution Intent v1 is compatible only with public authority responses and integration responses that preserve explicit separation between intent and execution.

| Upstream Surface | Compatible Version | Requirement |
| --- | --- | --- |
| Recovery Integration Response | `aer.runtime.recovery.integration_response.v1` | Must identify that execution authority is required or has been separately reviewed. |
| Recovery Execution Authority Response | `aer.runtime.recovery.execution_authority_response.v1` | Must preserve `executes_recovery: false` and separate authorization from execution. |
| Recovery Plan | `aer.runtime.recovery.plan.v1` | Must include a public execution boundary. |
| Recovery Execution Boundary | `aer.runtime.recovery.execution_boundary.v1` | Must be available for intent review. |

Downstream consumers remain incompatible until they define their own public contract and lifecycle gate.

## Intent Evolution Policy

Runtime Recovery Execution Intent v1 is stable for the Package 147 boundary.

Breaking changes require a new intent contract version. Breaking changes include:

- changing request or response field names
- removing required request or response fields
- changing allowed intent action meanings
- changing forbidden intent action meanings
- allowing this package to execute Recovery
- allowing this package to invoke downstream runtime consumers
- allowing this package to persist, replay, audit, journal, mutate, or call runtime modules
- replacing intent-only semantics with runtime behavior

Non-breaking changes may add clarifying prose, additional denied capabilities, or future downstream compatibility notes when v1 request and response meanings remain unchanged.

## GO / NO-GO

Final decision: GO.

Runtime Recovery Execution Intent Contract v1 is complete as an intent-only package.

The contract defines what authorized Recovery execution would intend to do without performing that execution.

Execution Intent MAY describe intended Recovery actions.

Execution Intent MUST NOT execute, schedule, dispatch, persist, replay, audit, journal, mutate, call runtime modules, or modify runtime execution modules.

Execution remains outside this package.

## Next Package

Next package: Package 148.

Package 148 should define the next downstream Recovery contract after execution intent is sealed, without implementing runtime execution.
