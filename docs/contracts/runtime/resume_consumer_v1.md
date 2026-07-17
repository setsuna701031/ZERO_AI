# AER Runtime Resume Consumer Contract v1

## Purpose

Define the Runtime Resume Consumer Contract v1 as the downstream public boundary after Runtime Resume Eligibility and Runtime Resume Planning.

Package 128 is contract/spec + seal only. It does not implement Runtime Resume Execution, does not execute a Resume Plan, and does not wire Resume to Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, or any runtime loop.

Runtime Resume Consumer Contract consumes only the public Resume Plan summary produced by `resume_plan_to_summary(...)` or an explicitly validated Resume Plan public contract. It must not consume Resume Plan internals, Snapshot Builder output, Snapshot private helpers, Snapshot Validator internals, runtime execution state, scheduler state, operator state, persistence records, audit records, journal events, replay streams, or recovery state.

The contract exists to prevent downstream domains from binding directly to Resume Planning internals. Downstream domains may consume only explicit future handoffs after their own domain contracts authorize them.

## Package Scope

Package 128 owns only the consumer boundary contract and its seal.

Package 128 does not add a runtime implementation module.

Package 128 does not modify `core/runtime/aer_runtime_resume_plan.py`.

Package 128 does not create consumer behavior, execution behavior, scheduler behavior, recovery behavior, operator behavior, dispatcher behavior, persistence behavior, audit behavior, journal behavior, replay behavior, or runtime mutation.

## Upstream Boundary

Runtime Resume Consumer Contract consumes only the public output of Runtime Resume Planning.

Allowed upstream inputs:

- Resume Plan public summary from `resume_plan_to_summary(...)`
- Validated Resume Plan public contract using schema `aer.runtime.resume.plan.v1`
- Data-only execution boundary descriptor using schema `aer.runtime.resume.execution_boundary.v1`

Forbidden upstream inputs:

- raw Snapshot Builder output
- Snapshot Builder private helper output
- Snapshot Validator internals
- Runtime Snapshot Consumer private helpers
- Resume Eligibility internals beyond its public summary when explicitly carried by a plan summary
- Resume Plan private helper state
- scheduler queues
- operator decisions
- dispatcher calls
- persistence handles
- audit handles
- journal handles
- replay streams
- recovery objects
- runtime execution state

The upstream boundary is projection-only. It preserves public identity, lineage, eligibility, status, reason, source outcome, source validity, and execution boundary evidence. It must not infer, repair, enrich, or execute.

## Downstream Boundary

Runtime Resume Consumer Contract produces only data-only consumer boundary descriptors.

Runtime Resume Execution remains outside Package 128.

Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, and Journal remain downstream domains.

Downstream domains may consume explicit future handoffs only after their own package contracts authorize them. Package 128 does not authorize any downstream domain to execute, schedule, recover, dispatch, operate, persist, audit, journal, or replay.

## Boundary Matrix

| Domain | Direction | Allowed | Forbidden |
| --- | --- | --- | --- |
| Runtime Resume Plan Summary | Upstream | Runtime Resume Consumer Contract may consume the public summary produced by `resume_plan_to_summary(...)`. | It must not consume private planning helpers or internal planning state. |
| Runtime Resume Plan Contract | Upstream | Runtime Resume Consumer Contract may describe validation over `aer.runtime.resume.plan.v1`. | It must not accept unknown Resume Plan fields, unvalidated payloads, runtime objects, or executable callables. |
| Runtime Snapshot Consumer | Upstream ancestor | It may appear only as public evidence already projected into the Resume Plan summary. | Package 128 must not call Snapshot Consumer, Snapshot Builder, or Snapshot Validator. |
| Snapshot Builder | Upstream ancestor | No direct dependency. | Package 128 must never consume Snapshot Builder output directly. |
| Snapshot Validation | Upstream ancestor | Validation evidence may be preserved only if already present in a public Resume Plan surface. | Package 128 must never duplicate Snapshot validation. |
| Resume Eligibility | Upstream ancestor | Eligibility may appear only through public plan fields and summaries. | Package 128 must not recompute eligibility. |
| Resume Planning | Upstream | Package 128 may reference `resume_plan_to_summary(...)` as the upstream public surface. | Package 128 must not modify planning implementation or plan builder behavior. |
| Resume Consumer Input | Internal output | Package 128 may define `aer.runtime.resume.consumer_input.v1` as a data-only boundary descriptor. | Consumer input must not execute, schedule, dispatch, recover, operate, persist, audit, journal, replay, or mutate runtime. |
| Resume Consumer Output | Internal output | Package 128 may define `aer.runtime.resume.consumer_output.v1` as a data-only validation/output descriptor. | Consumer output must not become a runtime execution result. |
| Runtime Resume Execution | Downstream | Future Runtime Resume Execution may consume an authorized handoff after a future contract defines that domain. | Execution is outside Package 128 and must not be hidden inside consumer input, output, validation, or summary. |
| Recovery | Downstream | Future Recovery may consume explicit future handoffs only. | Package 128 must not perform Recovery or recovery classification beyond descriptive future-domain notes. |
| Scheduler | Downstream | Future Scheduler may consume explicit future handoffs only. | Package 128 must not schedule, enqueue, select workers, or choose execution order. |
| Dispatcher | Downstream | Future Dispatcher may consume explicit future handoffs only. | Package 128 must not dispatch or construct dispatcher calls. |
| Operator | Downstream | Future Operator may consume explicit future handoffs only. | Package 128 must not call Operator or create operator decisions. |
| Persistence | Downstream | Future Persistence may consume explicit future records only. | Package 128 must not persist or create persistence handles. |
| Audit | Downstream | Future Audit may consume explicit future records only. | Package 128 must not audit or create audit handles. |
| Journal | Downstream | Future Journal may consume explicit future events only. | Package 128 must not journal, replay, emit events, or read event streams. |

## Schema Names

Runtime Resume Consumer Contract v1 defines three separate schema names:

- `aer.runtime.resume.consumer_input.v1`
- `aer.runtime.resume.consumer_output.v1`
- `aer.runtime.resume.consumer_boundary.v1`

These schemas represent separate responsibilities. Resume Planning, Resume Consumer Boundary, and Runtime Resume Execution must never collapse into one public API.

## Separate Responsibilities

### Resume Planning

Resume Planning owns eligibility and plan construction. It produces the public Resume Plan and Resume Plan summary.

Resume Planning does not own downstream consumption, runtime execution, recovery, scheduling, dispatch, operator behavior, persistence, audit, journal, replay, or runtime mutation.

### Resume Consumer Boundary

Resume Consumer Boundary owns the contract for safe downstream consumption of a Resume Plan public summary.

It may describe consumer input validation and consumer-safe summary projection. It must not implement the consumer behavior in Package 128.

It does not create runtime state, allocate runtime identity, bind workspaces, execute a Resume Plan, recover runtime, schedule work, dispatch work, call operator, persist, audit, journal, replay, or mutate runtime.

### Runtime Resume Execution

Runtime Resume Execution remains future-domain only.

Execution may consume an authorized future handoff only after a future execution-domain package defines ownership, API, validation, failure ownership, scheduler interaction, dispatcher interaction, operator interaction, persistence interaction, audit interaction, and journal interaction.

Execution must not be hidden inside Resume Planning, Resume Consumer Input, Resume Consumer Output, consumer validation, summaries, or metadata.

## Consumer Input Contract

Input: Resume Plan public summary or validated Resume Plan public contract.

Output: consumer input descriptor with schema `aer.runtime.resume.consumer_input.v1`.

Required consumer input fields:

- `contract`
- `resume_token`
- `eligible`
- `status`
- `reason`
- `snapshot_id`
- `lineage`
- `consumer_status`
- `execution_boundary`
- `source_valid`
- `source_outcome`
- `descriptive_only`

Allowed source outcomes:

- `ready_for_future_consumer`
- `blocked`
- `invalid_plan`
- `invalid_summary`
- `execution_not_authorized`

Blocked source outcomes:

- `blocked`
- `invalid_plan`
- `invalid_summary`
- `execution_not_authorized`

Consumer input rules:

- `resume_token` must come from the public Resume Plan summary or validated public Resume Plan.
- `snapshot_id` must come from the public Resume Plan summary or validated public Resume Plan.
- `lineage` must be the public lineage mapping from the Resume Plan summary or validated public Resume Plan.
- `execution_boundary` must use `aer.runtime.resume.execution_boundary.v1` and must preserve `execution_allowed: false` until a future execution-domain package changes that rule.
- `source_valid` records only whether the public source is structurally consumable.
- `source_outcome` records only the consumer-boundary classification.
- `descriptive_only` must be true.

Consumer input must not contain runtime objects, scheduler queues, operator decisions, dispatcher calls, persistence handles, audit handles, journal handles, replay handles, recovery objects, executable callables, file handles, process handles, environment handles, locks, leases, or reservations.

## Consumer Output Contract

Input: consumer input descriptor.

Output: consumer output descriptor with schema `aer.runtime.resume.consumer_output.v1`.

Required consumer output fields:

- `contract`
- `accepted_for_future_domain`
- `blocked`
- `status`
- `reason`
- `resume_token`
- `snapshot_id`
- `lineage`
- `execution_boundary`
- `consumer_boundary`
- `descriptive_only`

Allowed statuses:

- `accepted_for_future_domain`
- `blocked`
- `invalid_consumer_input`
- `execution_not_authorized`

Consumer output rules:

- `accepted_for_future_domain` means only that the descriptor is structurally safe for a future downstream domain contract to consider.
- `accepted_for_future_domain` does not mean runtime execution is allowed.
- `blocked` means only that the descriptor is not structurally safe for future-domain handoff.
- `consumer_boundary` must use schema `aer.runtime.resume.consumer_boundary.v1`.
- `descriptive_only` must be true.

Consumer output must not be interpreted as execution result, recovery result, scheduler result, dispatcher result, operator result, persistence record, audit record, journal event, or replay event.

## Consumer Boundary Contract

The consumer boundary schema is `aer.runtime.resume.consumer_boundary.v1`.

Required consumer boundary fields:

- `contract`
- `future_domain_only`
- `execution_allowed`
- `downstream_authorized`
- `allowed_future_domains`
- `reason`

Package 128 required values:

- `future_domain_only` must be true.
- `execution_allowed` must be false.
- `downstream_authorized` must be false.
- `allowed_future_domains` must be descriptive only.
- `reason` must state that downstream consumption requires future domain contracts.

The consumer boundary is not a scheduler admission token, dispatcher command, recovery trigger, operator decision, persistence record, audit event, journal event, replay token, or runtime execution permission.

## Consumer-Safe Summary Rule

Consumer-safe summaries may expose only these fields:

- `contract`
- `resume_token`
- `eligible`
- `status`
- `reason`
- `snapshot_id`
- `lineage`
- `consumer_status`
- `execution_boundary`
- `source_valid`
- `source_outcome`

Consumer-safe summaries must not expose:

- raw Resume Plan payloads
- private Resume Planning helper state
- raw Snapshot payloads
- Snapshot Builder output
- Snapshot Validator internals
- Runtime Snapshot Consumer private state
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

## Validation Contract

Validation reports are descriptive only. No auto-repair is allowed.

### Consumer Input Validation

- consumer input source must be a mapping
- source must be a Resume Plan public summary or validated Resume Plan public contract
- required public identity fields must be present
- `resume_token` must be a non-empty string
- `snapshot_id` must be a string or `None` only when the source is blocked
- `lineage` must be a mapping
- `execution_boundary` must be a mapping using schema `aer.runtime.resume.execution_boundary.v1`
- `execution_boundary.execution_allowed` must be false in Package 128
- unknown fields are prohibited
- runtime objects and executable callables are prohibited

### Consumer Output Validation

- consumer output payload must be a mapping
- `contract` must be `aer.runtime.resume.consumer_output.v1`
- required consumer output fields must be present
- unknown fields are prohibited
- `accepted_for_future_domain` and `blocked` must be booleans and must not conflict
- `consumer_boundary` must be a mapping using schema `aer.runtime.resume.consumer_boundary.v1`
- `descriptive_only` must be true
- runtime objects and executable callables are prohibited

### Consumer Boundary Validation

- consumer boundary payload must be a mapping
- `contract` must be `aer.runtime.resume.consumer_boundary.v1`
- required consumer boundary fields must be present
- unknown fields are prohibited
- `future_domain_only` must be true in Package 128
- `execution_allowed` must be false in Package 128
- `downstream_authorized` must be false in Package 128
- `allowed_future_domains` must be descriptive strings only

## Unknown Field Policy

Unknown fields are prohibited for consumer input, consumer output, and consumer boundary payloads.

Unknown fields must not be ignored, renamed, embedded in metadata, persisted, audited, journaled, replayed, passed through, or executed.

Package 128 must not use metadata as an escape hatch for unknown downstream fields.

## Required Field Policy

All required fields listed in the relevant contract section must be present.

Missing required fields are descriptive validation failures and must not be auto-repaired.

Package 128 must not generate missing runtime identity, scheduler identity, dispatcher identity, operator identity, persistence identity, audit identity, journal identity, recovery identity, or execution identity.

## Type Policy

Fields must use simple public contract values only: strings, booleans, `None`, lists of descriptive strings, and mappings of public scalar values.

Runtime objects, functions, methods, lambdas, file handles, process handles, scheduler queues, operator decisions, dispatcher callables, persistence handles, audit handles, journal handles, replay handles, recovery objects, locks, leases, reservations, and runtime execution objects are prohibited.

## Identity Policy

Consumer input and output must preserve `resume_token` and `snapshot_id` from the public Resume Plan surface.

Package 128 must not allocate runtime session identity.

Package 128 must not read runtime state to infer identity.

Package 128 must not copy identity from Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, Recovery, Replay, or runtime execution state.

## Lineage Policy

Lineage must come from the public Resume Plan surface.

Lineage mismatch or malformed lineage is descriptive only.

Package 128 must not repair lineage, infer lineage, merge lineage, normalize lineage from runtime state, or query downstream domains to complete lineage.

## Status Policy

Consumer input and output statuses are consumer-boundary statuses only.

They must not be interpreted as scheduler statuses, dispatcher statuses, operator statuses, persistence statuses, audit statuses, journal statuses, recovery statuses, replay statuses, or runtime execution statuses.

## Error Taxonomy

Each failure belongs to exactly one category:

| Failure | Category | Owner |
| --- | --- | --- |
| source is not a mapping | Consumer Input Error | Resume Consumer Boundary |
| invalid Resume Plan summary shape | Consumer Input Error | Resume Consumer Boundary |
| invalid Resume Plan contract | Compatibility Error | Resume Consumer Boundary |
| missing resume token | Identity Error | Resume Consumer Boundary |
| missing or malformed snapshot identity | Identity Error | Resume Consumer Boundary |
| malformed lineage | Lineage Error | Resume Consumer Boundary |
| execution boundary allows execution | Execution Boundary Error | Resume Consumer Boundary |
| unknown consumer input fields | Compatibility Error | Resume Consumer Boundary |
| unknown consumer output fields | Compatibility Error | Resume Consumer Boundary |
| callable or runtime object in payload | Safety Error | Resume Consumer Boundary |
| downstream domain tries to execute | Ownership Violation | Future Runtime Resume Execution |
| recovery consumes without future contract | Ownership Violation | Future Recovery |
| scheduler consumes without future contract | Ownership Violation | Future Scheduler |
| dispatcher consumes without future contract | Ownership Violation | Future Dispatcher |
| operator consumes without future contract | Ownership Violation | Future Operator |
| persistence consumes without future contract | Ownership Violation | Future Persistence |
| audit consumes without future contract | Ownership Violation | Future Audit |
| journal consumes without future contract | Ownership Violation | Future Journal |

## Responsibility Matrix

| Capability | Owner | Package 128 Allowed | Package 128 Forbidden |
| --- | --- | --- | --- |
| Resume Plan construction | Runtime Resume Planning | Reference public summary only. | Modify builder behavior. |
| Resume Plan validation | Runtime Resume Planning | Require validated public plan or public summary. | Duplicate planning internals. |
| Consumer input contract | Runtime Resume Consumer Boundary | Define data-only schema and validation rules. | Execute or hand off to runtime. |
| Consumer output contract | Runtime Resume Consumer Boundary | Define data-only schema and validation rules. | Treat output as runtime result. |
| Consumer boundary descriptor | Runtime Resume Consumer Boundary | Define future-domain-only descriptor. | Authorize downstream execution. |
| Runtime Resume Execution | Future Runtime Resume Execution | None. | Implement execution. |
| Recovery | Future Recovery | None. | Recover or classify by reading recovery state. |
| Scheduler | Future Scheduler | None. | Schedule or enqueue work. |
| Dispatcher | Future Dispatcher | None. | Dispatch work. |
| Operator | Future Operator | None. | Call operator or create operator decisions. |
| Persistence | Future Persistence | None. | Persist data. |
| Audit | Future Audit | None. | Emit audit records. |
| Journal | Future Journal | None. | Emit or replay journal events. |

## Public API Contract

Package 128 is contract/spec + seal only. It does not implement public runtime functions.

Future implementation packages may define these consumer-boundary helpers only after a package explicitly authorizes implementation:

- `build_resume_consumer_input(...)`
- `validate_resume_consumer_input(...)`
- `build_resume_consumer_output(...)`
- `validate_resume_consumer_output(...)`
- `resume_consumer_input_to_summary(...)`
- `resume_consumer_output_to_summary(...)`

Forbidden public APIs for Package 128 and any consumer-boundary package unless a future execution-domain package authorizes them:

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

## Forbidden Imports and Calls

Package 128 must not import or call:

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

Package 128 must not call:

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

Consumer boundary contracts are descriptive only.

Package 128 must not read or write files, mutate stores, mutate journals, mutate audit logs, mutate scheduler queues, mutate operator state, mutate dispatcher state, mutate persistence records, mutate recovery state, or mutate runtime execution state.

## GO / NO-GO Decision

Final decision: GO.

Runtime Resume Consumer Contract is ready as a contract/spec + seal boundary.

Runtime Resume Execution remains future-domain only.

Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, and Journal remain downstream domains and are not authorized by Package 128.

## Implementation Readiness

Ready for Package 129: Runtime Resume Integration Blueprint.

Package 129 should define the architecture for how Resume Consumer Boundary may hand off to future downstream domains without implementing execution, recovery, scheduling, dispatch, operator behavior, persistence, audit, journal, or replay.

Package 130 should begin Runtime Recovery Blueprint only after Package 129 is sealed.
