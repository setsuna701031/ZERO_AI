# Runtime Recovery Executor Boundary Contract v1

## Executor Boundary Purpose

Package 150 defines the Runtime Recovery Executor Boundary before any real executor implementation exists.

This package defines the public boundary around future executor input and output data.

It does NOT implement executor behavior.

The executor boundary may describe what a future executor would require, but it MUST NOT execute Recovery, schedule, dispatch, operate, supervise, persist, replay, audit, journal, mutate runtime state, perform file IO, call subprocess, or call runtime execution modules.

## Executor Input Schema

An Executor Boundary Input is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.executor_boundary_input.v1`. |
| `executor_boundary_id` | string | Yes | Stable caller-provided boundary identifier. |
| `bridge_reference` | mapping | Yes | Data-only reference to Package 149 bridge response. |
| `authority_reference` | mapping | Yes | Data-only reference to Package 146 authority response. |
| `intent_reference` | mapping | Yes | Data-only reference to Package 147 intent response. |
| `requested_executor_scope` | string | Yes | Requested executor-boundary scope. |
| `metadata` | mapping | Yes | Caller metadata for future executor boundary consumers. |
| `boundary_only` | boolean | Yes | Must be `true`. |

Allowed `requested_executor_scope` values:

- `executor_boundary_review_only`
- `future_executor_input_shape_review`
- `side_effect_boundary_review`

## Executor Output Schema

An Executor Boundary Output is a plain mapping with exactly these fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract` | string | Yes | Must be `aer.runtime.recovery.executor_boundary_output.v1`. |
| `executor_boundary_id` | string or null | Yes | Mirrors the input boundary identifier when available. |
| `accepted` | boolean | Yes | Whether input is accepted as executor-boundary data. |
| `status` | string | Yes | Boundary status from this contract's taxonomy. |
| `bridge_reference` | mapping | Yes | Copied data-only bridge reference. |
| `authority_reference` | mapping | Yes | Copied data-only authority reference. |
| `intent_reference` | mapping | Yes | Copied data-only intent reference. |
| `allowed_responsibilities` | list of strings | Yes | Responsibilities allowed by this boundary package. |
| `denied_responsibilities` | list of strings | Yes | Responsibilities forbidden by this boundary package. |
| `side_effects_allowed` | boolean | Yes | Must be `false`. |
| `runtime_mutation_allowed` | boolean | Yes | Must be `false`. |
| `executes_recovery` | boolean | Yes | Must be `false`. |
| `reason` | string or null | Yes | Human-readable response reason. |
| `boundary_only` | boolean | Yes | Must be `true`. |

Boundary acceptance does not implement an executor and does not authorize runtime effects.

## Required Bridge Reference

Every valid Executor Boundary Input must include a data-only reference to:

- `aer.runtime.recovery.runtime_bridge_request.v1`
- `aer.runtime.recovery.runtime_bridge_response.v1`

The bridge reference must preserve passive bridge semantics, `bridge_only: true`, and `executes_recovery: false`.

## Required Authority Reference

Every valid Executor Boundary Input must include a data-only reference to:

- `aer.runtime.recovery.execution_authority_request.v1`
- `aer.runtime.recovery.execution_authority_response.v1`

The authority reference must preserve Package 146 authority-only semantics and `executes_recovery: false`.

## Required Intent Reference

Every valid Executor Boundary Input must include a data-only reference to:

- `aer.runtime.recovery.execution_intent_request.v1`
- `aer.runtime.recovery.execution_intent_response.v1`

The intent reference must preserve Package 147 intent-only semantics and `executes_recovery: false`.

## Allowed Executor Responsibilities

Allowed executor responsibilities for this boundary are descriptive only:

- define future executor input shape
- define future executor output shape
- describe required bridge reference
- describe required authority reference
- describe required intent reference
- describe side-effect denial
- describe runtime mutation denial
- identify denied executor responsibilities
- prepare future executor package review

Allowed responsibilities do not perform Recovery execution.

## Forbidden Executor Responsibilities

Forbidden executor responsibilities include:

- execute Recovery
- schedule runtime work
- dispatch runtime commands
- invoke Operator runtime behavior
- invoke runtime supervisor behavior
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

## Side-Effect Boundary

Package 150 allows no side effects.

Executor Boundary Output must set:

- `side_effects_allowed` to `false`
- `executes_recovery` to `false`
- `boundary_only` to `true`

No package consumer may treat boundary acceptance as permission to perform runtime work.

## Runtime Mutation Boundary

Package 150 allows no runtime mutation.

Executor Boundary Output must set:

- `runtime_mutation_allowed` to `false`
- `executes_recovery` to `false`
- `boundary_only` to `true`

Runtime mutation remains outside this package.

## Failure Taxonomy

Executor Boundary outputs use this failure taxonomy:

| Status | Meaning | Recovery Execution |
| --- | --- | --- |
| `accepted_boundary_only` | Boundary input is accepted as descriptive executor-boundary data. | Not performed |
| `invalid_executor_boundary_input` | Input shape or contract identifier is invalid. | Not performed |
| `missing_bridge_reference` | Required bridge reference is absent. | Not performed |
| `incompatible_bridge_reference` | Bridge reference is incompatible with Package 149. | Not performed |
| `missing_authority_reference` | Required authority reference is absent. | Not performed |
| `incompatible_authority_reference` | Authority reference is incompatible with Package 146. | Not performed |
| `missing_intent_reference` | Required intent reference is absent. | Not performed |
| `incompatible_intent_reference` | Intent reference is incompatible with Package 147. | Not performed |
| `forbidden_executor_responsibility` | Input attempts to cross into executor behavior. | Not performed |

Failures are data-only outcomes.

## Dependency Rules

Runtime Recovery Executor Boundary v1 may depend only on public Recovery contracts:

```text
Runtime Recovery Execution Authority Contract v1
  -> Runtime Recovery Execution Intent Contract v1
  -> Runtime Recovery Runtime Bridge Contract v1
  -> Runtime Recovery Executor Boundary Contract v1
```

Allowed public references:

- `aer.runtime.recovery.execution_authority_response.v1`
- `aer.runtime.recovery.execution_intent_response.v1`
- `aer.runtime.recovery.runtime_bridge_response.v1`
- `aer.runtime.recovery.executor_boundary_input.v1`
- `aer.runtime.recovery.executor_boundary_output.v1`

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

Runtime Recovery Executor Boundary v1 is compatible only with passive bridge, authority, and intent references that deny execution.

| Upstream Surface | Compatible Version | Requirement |
| --- | --- | --- |
| Runtime Recovery Runtime Bridge Response | `aer.runtime.recovery.runtime_bridge_response.v1` | Must preserve bridge-only semantics and `executes_recovery: false`. |
| Recovery Execution Authority Response | `aer.runtime.recovery.execution_authority_response.v1` | Must preserve authority-only semantics and `executes_recovery: false`. |
| Recovery Execution Intent Response | `aer.runtime.recovery.execution_intent_response.v1` | Must preserve intent-only semantics and `executes_recovery: false`. |

A real executor remains incompatible until a future package explicitly defines and authorizes executor behavior.

## GO / NO-GO

Final decision: GO.

Runtime Recovery Executor Boundary Contract v1 is complete as a boundary-only package.

The package defines executor input and output boundaries before executor implementation.

It does not implement executor behavior.

Recovery execution remains outside this package.

## Next Package

Next package: Package 151.

Package 151 should define the next downstream Recovery runtime preparation layer without implementing real executor behavior unless explicitly scoped by a future package.
