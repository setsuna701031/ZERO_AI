# AER Runtime Resume Execution Contract v1

## Purpose

Package 131 defines the public contract for Runtime Resume Execution after the Runtime Resume Execution Blueprint and before any Runtime Resume Execution validation or implementation package.

This package is contract/spec + seal only. It does not implement runtime resume execution, does not create a runtime execution module, does not execute a Resume Plan, and does not wire Runtime Resume Execution to Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, Replay, TaskRunner, or any runtime loop.

Runtime Resume Execution Contract v1 exists to define the data boundary for a future execution domain. It turns the Package 130 blueprint into stable public schemas, ownership rules, validation responsibilities, failure vocabulary, and future API names without adding behavior.

## Package Scope

Package 131 owns only this contract specification and its focused seal.

Package 131 does not add runtime behavior.

Package 131 does not add `core/runtime/aer_runtime_resume_execution.py`.

Package 131 does not modify Runtime Resume Planning, Runtime Resume Consumer Contract, Runtime Snapshot, Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, Replay, TaskRunner, or runtime loop modules.

Package 131 does not authorize execution. Execution implementation remains future-domain only.

## Upstream Boundary

Runtime Resume Execution Contract consumes only the Runtime Resume Consumer public boundary defined by Package 128 and positioned by Package 130.

Allowed upstream source for future execution request construction:

- `aer.runtime.resume.consumer_output.v1`
- `aer.runtime.resume.consumer_boundary.v1`
- public identity fields preserved by Resume Consumer Output: `resume_token`, `snapshot_id`, and `lineage`
- public status fields preserved by Resume Consumer Output: `accepted_for_future_domain`, `blocked`, `status`, and `reason`
- data-only execution boundary descriptor with `execution_allowed: false` until a future implementation package explicitly changes execution admission under this contract

Forbidden upstream sources:

- raw Resume Plan payloads
- Resume Plan private helper state
- Resume Eligibility internals
- Snapshot Builder output
- Snapshot Validator internals
- Runtime Snapshot Consumer private helpers
- scheduler queues
- dispatcher calls
- operator decisions
- persistence handles
- audit handles
- journal handles
- replay streams
- recovery objects
- runtime execution state
- runtime objects
- callables
- file handles
- process handles
- environment handles
- locks
- leases
- reservations

Runtime Resume Execution Contract must not consume Resume Plan internals directly. Resume Consumer Output is the only authorized upstream public surface for future execution request construction.

## Downstream Boundary

Runtime Resume Execution Contract produces only public execution data contracts.

Package 131 does not authorize any downstream domain to consume these contracts as live behavior.

Downstream domains remain future domains:

- Recovery owns recovery decisions, recovery classification, and recovery policies.
- Scheduler owns scheduling, queueing, worker selection, retry timing, and execution admission into scheduler-owned surfaces.
- Dispatcher owns dispatch commands and execution routing.
- Operator owns operator-facing decisions, approvals, issue handling, and operator policy.
- Persistence owns durable records and stores.
- Audit owns audit records.
- Journal owns journal events and replay streams.
- Replay owns replay behavior.

Runtime Resume Execution may only hand off to these domains after each downstream domain has its own future contract authorizing that handoff.

## Boundary Matrix

| Domain | Direction | Allowed | Forbidden |
| --- | --- | --- | --- |
| Resume Consumer Output | Upstream | Execution Contract may define request construction from `aer.runtime.resume.consumer_output.v1`. | It must not modify Resume Consumer Output or interpret it as permission to execute in Package 131. |
| Resume Consumer Boundary | Upstream | Execution Contract may preserve boundary evidence. | It must not bypass `downstream_authorized: false` in Package 128 surfaces. |
| Resume Planning | Upstream ancestor | May appear only through public fields projected into Resume Consumer Output. | Must not consume raw plan internals, plan private helpers, or recompute planning. |
| Runtime Snapshot Consumer | Upstream ancestor | May appear only as public lineage and identity evidence already projected downstream. | Must not call Snapshot Consumer, Snapshot Builder, or Snapshot Validator. |
| Runtime Resume Execution Request | Internal output | May define `aer.runtime.resume.execution_request.v1`. | Request must not execute, schedule, dispatch, recover, operate, persist, audit, journal, replay, or mutate runtime. |
| Runtime Resume Execution Result | Internal output | May define `aer.runtime.resume.execution_result.v1`. | Result must not be treated as Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, or Replay output. |
| Runtime Resume Execution Failure | Internal output | May define `aer.runtime.resume.execution_failure.v1`. | Failure must not perform recovery, retry, schedule, dispatch, or operator action. |
| Recovery | Downstream | Future Recovery may consume an explicit execution result or failure after a future Recovery contract authorizes it. | Package 131 must not recover or classify using recovery state. |
| Scheduler | Downstream | Future Scheduler may consume an explicit future handoff after Scheduler contract authorization. | Package 131 must not schedule, enqueue, select workers, or choose execution order. |
| Dispatcher | Downstream | Future Dispatcher may consume a future dispatch handoff after Dispatcher contract authorization. | Package 131 must not dispatch or construct dispatcher calls. |
| Operator | Downstream | Future Operator may consume summaries, approval needs, or issues after Operator contract authorization. | Package 131 must not call Operator or create operator decisions. |
| Persistence | Downstream | Future Persistence may persist execution records after a future Persistence contract authorizes it. | Package 131 must not persist or create persistence handles. |
| Audit | Downstream | Future Audit may record execution evidence after a future Audit contract authorizes it. | Package 131 must not audit or create audit handles. |
| Journal | Downstream | Future Journal may emit execution events after a future Journal contract authorizes it. | Package 131 must not journal, replay, emit events, or read event streams. |
| Replay | Downstream | Future Replay may consume journaled records after a future Replay contract authorizes it. | Package 131 must not replay. |

## Schema Names

Runtime Resume Execution Contract v1 defines three separate public schema names:

- `aer.runtime.resume.execution_request.v1`
- `aer.runtime.resume.execution_result.v1`
- `aer.runtime.resume.execution_failure.v1`

These schemas represent separate responsibilities. Execution Request, Execution Result, and Execution Failure must never collapse into one public API.

## Separate Responsibilities

### Execution Request

Execution Request is the public data contract for a future attempt to execute an authorized resume handoff.

Execution Request does not execute. It does not recover, schedule, dispatch, operate, persist, audit, journal, replay, allocate runtime identity, bind workspaces, bind repositories, or mutate runtime state.

### Execution Result

Execution Result is the public data contract for a future execution-domain outcome.

Execution Result records only execution-domain status and public identity evidence. It is not a scheduler result, dispatcher result, recovery result, operator result, persistence record, audit record, journal event, replay event, or runtime loop state.

### Execution Failure

Execution Failure is the public data contract for execution-domain failure classification.

Execution Failure describes failures only. It must not perform recovery, schedule retries, dispatch work, create operator decisions, persist records, audit records, journal events, replay streams, or mutate runtime.

## Execution Request Contract

Input: Runtime Resume Consumer Output public contract.

Output: execution request with schema `aer.runtime.resume.execution_request.v1`.

Required execution request fields:

- `contract`
- `execution_request_id`
- `resume_token`
- `snapshot_id`
- `lineage`
- `source_contract`
- `source_status`
- `source_reason`
- `execution_allowed`
- `requested_action`
- `preconditions`
- `failure_policy`
- `metadata`
- `descriptive_only`

Allowed requested actions:

- `resume_runtime`
- `validate_only`
- `blocked`

Package 131 required request behavior:

- `execution_allowed` must be false in Package 131.
- `requested_action` is descriptive only.
- `preconditions` must be a data-only mapping.
- `failure_policy` must be a data-only mapping.
- `metadata` must be a data-only mapping.
- `descriptive_only` must be true.

Execution Request must not contain runtime objects, scheduler queues, operator decisions, dispatcher calls, persistence handles, audit handles, journal handles, replay handles, recovery objects, executable callables, file handles, process handles, environment handles, locks, leases, or reservations.

## Execution Result Contract

Input: future Execution Request.

Output: execution result with schema `aer.runtime.resume.execution_result.v1`.

Required execution result fields:

- `contract`
- `execution_request_id`
- `resume_token`
- `snapshot_id`
- `lineage`
- `status`
- `reason`
- `completed`
- `failed`
- `failure`
- `downstream_handoff_required`
- `downstream_handoff_type`
- `metadata`
- `descriptive_only`

Allowed statuses:

- `not_started`
- `blocked`
- `validated`
- `completed`
- `failed`
- `handoff_required`

Package 131 required result behavior:

- Execution Result is contract-only and descriptive in Package 131.
- `completed` and `failed` must be booleans and must not conflict.
- `failure` must be `None` or an `aer.runtime.resume.execution_failure.v1` payload.
- `downstream_handoff_required` must be descriptive only.
- `downstream_handoff_type` must be `None` or one of `recovery`, `scheduler`, `dispatcher`, `operator`, `persistence`, `audit`, `journal`, or `replay`.
- `metadata` must be a data-only mapping.
- `descriptive_only` must be true.

Execution Result must not be interpreted as permission for Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, Replay, or runtime loop behavior.

## Execution Failure Contract

Input: execution-domain failure condition.

Output: execution failure with schema `aer.runtime.resume.execution_failure.v1`.

Required execution failure fields:

- `contract`
- `failure_code`
- `category`
- `owner`
- `reason`
- `recoverable`
- `downstream_owner`
- `metadata`
- `descriptive_only`

Allowed failure codes:

- `invalid_execution_request`
- `invalid_consumer_output`
- `consumer_boundary_violation`
- `execution_not_authorized`
- `precondition_failed`
- `lineage_mismatch`
- `identity_mismatch`
- `unsupported_requested_action`
- `future_domain_required`
- `downstream_contract_missing`
- `runtime_execution_failed`
- `ownership_violation`

Allowed categories:

- `Compatibility Error`
- `Consumer Boundary Error`
- `Execution Boundary Error`
- `Precondition Error`
- `Lineage Error`
- `Identity Error`
- `Status Error`
- `Future Domain Required`
- `Runtime Execution Error`
- `Ownership Violation`

Allowed owners:

- `Runtime Resume Execution`
- `Runtime Resume Consumer Boundary`
- `Future Recovery`
- `Future Scheduler`
- `Future Dispatcher`
- `Future Operator`
- `Future Persistence`
- `Future Audit`
- `Future Journal`
- `Future Replay`

Execution Failure must not trigger recovery, retry, scheduling, dispatch, operator action, persistence, audit, journal, replay, or runtime mutation.

## Public API Contract

Package 131 is contract/spec + seal only. It does not implement public runtime functions.

Future implementation packages may define these helpers only after a package explicitly authorizes implementation:

- `create_execution_request(...)`
- `validate_execution_request(...)`
- `create_execution_result(...)`
- `validate_execution_result(...)`
- `create_execution_failure(...)`
- `validate_execution_failure(...)`
- `execution_request_to_summary(...)`
- `execution_result_to_summary(...)`
- `execution_failure_to_summary(...)`

Forbidden public APIs for Package 131 and any execution contract package unless a future implementation package authorizes them:

- `resume(...)`
- `execute_resume(...)`
- `recover(...)`
- `schedule(...)`
- `dispatch(...)`
- `operate(...)`
- `persist(...)`
- `audit(...)`
- `journal(...)`
- `replay(...)`

## Validation Contract

Validation reports are descriptive only. No auto-repair is allowed.

### Execution Request Validation

- request payload must be a mapping
- `contract` must be `aer.runtime.resume.execution_request.v1`
- required request fields must be present
- unknown fields are prohibited
- `execution_request_id`, `resume_token`, `snapshot_id`, `source_contract`, `source_status`, and `requested_action` must be strings or `None` only where explicitly permitted
- `lineage`, `preconditions`, `failure_policy`, and `metadata` must be mappings
- `execution_allowed` must be false in Package 131
- `descriptive_only` must be true
- runtime objects and executable callables are prohibited

### Execution Result Validation

- result payload must be a mapping
- `contract` must be `aer.runtime.resume.execution_result.v1`
- required result fields must be present
- unknown fields are prohibited
- `status` must be in the allowed status vocabulary
- `completed` and `failed` must be booleans and must not conflict
- `failure` must be `None` or a valid execution failure payload
- `metadata` must be a mapping
- `descriptive_only` must be true
- runtime objects and executable callables are prohibited

### Execution Failure Validation

- failure payload must be a mapping
- `contract` must be `aer.runtime.resume.execution_failure.v1`
- required failure fields must be present
- unknown fields are prohibited
- `failure_code`, `category`, `owner`, and `reason` must be strings
- `failure_code` must be in the allowed failure vocabulary
- `category` must be in the allowed category vocabulary
- `owner` must be in the allowed owner vocabulary
- `recoverable` must be boolean
- `metadata` must be a mapping
- `descriptive_only` must be true
- runtime objects and executable callables are prohibited

## Unknown Field Policy

Unknown fields are prohibited for execution request, execution result, and execution failure payloads.

Unknown fields must not be ignored, renamed, embedded in metadata, persisted, audited, journaled, replayed, passed through, or executed.

Package 131 must not use metadata as an escape hatch for unknown downstream fields.

## Required Field Policy

All required fields listed in the relevant contract section must be present.

Missing required fields are descriptive validation failures and must not be auto-repaired.

Package 131 must not generate missing runtime identity, scheduler identity, dispatcher identity, operator identity, persistence identity, audit identity, journal identity, recovery identity, replay identity, or execution identity from runtime state.

## Type Policy

Fields must use simple public contract values only: strings, booleans, `None`, lists of descriptive strings, and mappings of public scalar values.

Runtime objects, functions, methods, lambdas, file handles, process handles, scheduler queues, operator decisions, dispatcher callables, persistence handles, audit handles, journal handles, replay handles, recovery objects, locks, leases, reservations, and runtime execution objects are prohibited.

## Identity Policy

Execution Request and Execution Result must preserve `resume_token` and `snapshot_id` from the public Resume Consumer Output surface.

Package 131 must not allocate runtime session identity.

Package 131 must not read runtime state to infer identity.

Package 131 must not copy identity from Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, Recovery, Replay, or runtime execution state.

## Lineage Policy

Lineage must come from the public Resume Consumer Output surface.

Lineage mismatch or malformed lineage is descriptive only.

Package 131 must not repair lineage, infer lineage, merge lineage, normalize lineage from runtime state, or query downstream domains to complete lineage.

## Status Policy

Execution statuses are execution-domain statuses only.

They must not be interpreted as scheduler statuses, dispatcher statuses, operator statuses, persistence statuses, audit statuses, journal statuses, recovery statuses, replay statuses, or runtime loop statuses.

## Failure Ownership Matrix

| Failure | Failure code | Category | Owner |
| --- | --- | --- | --- |
| invalid execution request | `invalid_execution_request` | Compatibility Error | Runtime Resume Execution |
| invalid consumer output | `invalid_consumer_output` | Consumer Boundary Error | Runtime Resume Consumer Boundary |
| consumer boundary violation | `consumer_boundary_violation` | Consumer Boundary Error | Runtime Resume Consumer Boundary |
| execution not authorized | `execution_not_authorized` | Execution Boundary Error | Runtime Resume Execution |
| precondition failed | `precondition_failed` | Precondition Error | Runtime Resume Execution |
| lineage mismatch | `lineage_mismatch` | Lineage Error | Runtime Resume Execution |
| identity mismatch | `identity_mismatch` | Identity Error | Runtime Resume Execution |
| unsupported requested action | `unsupported_requested_action` | Status Error | Runtime Resume Execution |
| future domain required | `future_domain_required` | Future Domain Required | Runtime Resume Execution |
| downstream contract missing | `downstream_contract_missing` | Future Domain Required | Runtime Resume Execution |
| runtime execution failed | `runtime_execution_failed` | Runtime Execution Error | Runtime Resume Execution |
| ownership violation | `ownership_violation` | Ownership Violation | Runtime Resume Execution |

Failures are descriptive. They do not trigger recovery, retry, scheduling, dispatch, operator action, persistence, audit, journal, replay, or runtime mutation in Package 131.

## Dependency Graph

Allowed future contract direction:

```text
Runtime Resume Consumer Output
  -> Runtime Resume Execution Request
  -> Runtime Resume Execution Result
  -> Runtime Resume Execution Failure
  -> Future domain handoff contracts
```

Forbidden dependency direction:

```text
Runtime Resume Execution
  -> Scheduler internals
Runtime Resume Execution
  -> Recovery internals
Runtime Resume Execution
  -> Dispatcher internals
Runtime Resume Execution
  -> Operator internals
Runtime Resume Execution
  -> Persistence internals
Runtime Resume Execution
  -> Audit internals
Runtime Resume Execution
  -> Journal internals
Runtime Resume Execution
  -> Replay internals
Runtime Resume Execution
  -> Snapshot Builder
Runtime Resume Execution
  -> Resume Plan internals
```

## Forbidden Imports and Calls

Package 131 must not import or call:

- Scheduler
- TaskRunner
- Recovery
- Dispatcher
- Operator
- Persistence
- Audit
- Journal
- Replay
- Runtime execution modules
- Runtime loop modules
- Operator loop modules
- Snapshot Builder
- Snapshot Validator private helpers
- Resume Planning private helpers

Package 131 must not call:

- `resume(...)`
- `execute_resume(...)`
- `recover(...)`
- `schedule(...)`
- `dispatch(...)`
- `operate(...)`
- `persist(...)`
- `audit(...)`
- `journal(...)`
- `replay(...)`

## No Runtime Mutation

Execution contracts are descriptive only.

Package 131 must not read or write files, mutate stores, mutate journals, mutate audit logs, mutate scheduler queues, mutate operator state, mutate dispatcher state, mutate persistence records, mutate recovery state, mutate replay state, or mutate runtime execution state.

## GO / NO-GO Decision

Final decision: GO.

Runtime Resume Execution Contract v1 is ready as contract/spec + seal only.

Runtime Resume Execution implementation remains future-domain only.

Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, and Replay remain downstream domains and are not authorized by Package 131.

## Implementation Readiness

Ready for Package 132: Runtime Resume Execution Validation.

Package 132 may implement validation helpers for the Execution Request, Execution Result, and Execution Failure contracts only. Package 132 must not implement execution behavior.

## Non-mainline Issues Found

- Pre-existing untracked AER governance/runtime/docs/tests files and package sequence edits may exist in the worktree. Package 131 preserves unrelated worktree noise and changes only the requested execution contract document, contract seal test, and package sequence entry.
