# AER Runtime Resume Contract v1

## Purpose

Define Runtime Resume v1 as a public contract boundary after Runtime Snapshot Consumer and before any future Runtime Resume Execution domain.

Runtime Resume v1 is contract/spec + seal only. It does not implement runtime resume, does not modify runtime behavior, and does not create a runtime resume implementation module.

Runtime Resume v1 consumes Snapshot Consumer public result only. It does not consume raw Snapshot Builder output, Snapshot private helpers, Snapshot Validator internals, Resume Summary internals, runtime execution state, scheduler state, operator state, persistence records, audit records, journal events, replay streams, or recovery state.

## Upstream Boundary

Runtime Resume Contract consumes only Runtime Snapshot Consumer public result.

Runtime Resume Contract must never consume Snapshot Builder output directly.

Runtime Resume Contract must never duplicate Snapshot validation.

The upstream boundary is descriptive and public-contract only. It preserves consumer result identity, status, validation evidence, and lineage as public inputs to eligibility and planning.

## Downstream Boundary

Runtime Resume Contract produces only Resume Eligibility and Resume Plan public contracts.

Runtime Resume Execution is outside Package 126.

Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, and Journal remain downstream domains.

Downstream domains may consume explicit future handoffs only after their own package contracts authorize them. Package 126 does not define or perform downstream runtime behavior.

## Boundary Matrix

| Domain | Direction | Allowed | Forbidden |
| --- | --- | --- | --- |
| Runtime Snapshot Consumer | Upstream | Runtime Resume may consume the Runtime Snapshot Consumer public result. | Runtime Resume must not call consumer private helpers or treat the consumer as an execution gateway. |
| Snapshot Builder | Upstream | No direct dependency. | Runtime Resume must never consume Snapshot Builder output directly. |
| Snapshot Validation | Upstream | Runtime Resume may preserve validation evidence already present in the consumer result. | Runtime Resume must never duplicate Snapshot validation. |
| Resume Eligibility | Internal output | Runtime Resume may produce `aer.runtime.resume.eligibility.v1`. | Eligibility must not create runtime state, create a Resume Plan, or execute runtime. |
| Resume Planning | Internal output | Runtime Resume may produce `aer.runtime.resume.plan.v1`. | Planning must not execute the plan or modify runtime. |
| Runtime Resume Execution | Downstream | Future Runtime Resume Execution may consume a Resume Plan after a future contract authorizes it. | Execution is outside Package 126 and must not be hidden inside eligibility or planning. |
| Recovery | Downstream | Future Recovery may consume explicit future handoffs only. | Package 126 must not perform Recovery. |
| Scheduler | Downstream | Future Scheduler may consume explicit future handoffs only. | Package 126 must not schedule. |
| Dispatcher | Downstream | Future Dispatcher may consume explicit future handoffs only. | Package 126 must not dispatch. |
| Operator | Downstream | Future Operator may consume explicit future handoffs only. | Package 126 must not call Operator. |
| Persistence | Downstream | Future Persistence may consume explicit future records only. | Package 126 must not persist. |
| Audit | Downstream | Future Audit may consume explicit future records only. | Package 126 must not audit. |
| Journal | Downstream | Future Journal may consume explicit future events only. | Package 126 must not journal or replay. |

## Schema Names

Runtime Resume v1 defines three separate schema names:

- `aer.runtime.resume.eligibility.v1`
- `aer.runtime.resume.plan.v1`
- `aer.runtime.resume.execution_boundary.v1`

These schemas represent separate responsibilities. Resume Eligibility, Resume Planning, and Resume Execution Boundary must never collapse into one public API.

## Separate Responsibilities

### Resume Eligibility

Resume Eligibility determines whether resume is permitted.

It produces only a descriptive eligibility decision. It shall not create runtime state, create a Resume Plan, execute a plan, schedule, dispatch, recover, call operator, persist, audit, journal, replay, or execute runtime.

### Resume Planning

Resume Planning produces a deterministic Resume Plan.

It consumes an eligibility decision and Runtime Snapshot Consumer public result. It shall not execute the plan, modify runtime, schedule, dispatch, recover, call operator, persist, audit, journal, replay, or execute runtime.

### Resume Execution Boundary

Resume Execution Boundary describes the future-domain boundary only.

Execution is future-domain only. Package 126 does not implement execution. A Resume Plan may be consumed later by Runtime Resume Execution after a future package defines that domain. Execution must not be hidden inside eligibility or planning.

Resume Eligibility, Resume Planning, and Resume Execution Boundary must never collapse into one public API.

## Eligibility Contract

Input: Runtime Snapshot Consumer public result.

Output: eligibility decision with schema `aer.runtime.resume.eligibility.v1`.

Required eligibility fields:

- `contract`
- `eligible`
- `blocked`
- `status`
- `reason`
- `snapshot_id`
- `lineage`
- `consumer_status`
- `validation`
- `descriptive_only`

Allowed statuses:

- `eligible`
- `blocked`
- `invalid_snapshot`
- `invalid_consumer_result`
- `missing_identity`
- `lineage_mismatch`
- `unsupported_status`
- `recovery_required`

Blocked statuses:

- `blocked`
- `invalid_snapshot`
- `invalid_consumer_result`
- `missing_identity`
- `lineage_mismatch`
- `unsupported_status`
- `recovery_required`

Missing identity behavior:

- missing `snapshot_id` produces status `missing_identity`
- missing identity is not repaired, generated, persisted, recovered, or inferred
- missing identity belongs to Identity Error

Lineage mismatch behavior:

- mismatched or malformed lineage produces status `lineage_mismatch`
- lineage mismatch is descriptive only
- lineage mismatch belongs to Lineage Error

Invalid snapshot behavior:

- invalid Snapshot is reported only through the Runtime Snapshot Consumer public result
- Resume Eligibility must not call Snapshot Builder directly
- Resume Eligibility must not duplicate Snapshot validation logic
- invalid Snapshot belongs to Snapshot Error when the consumer result reports Snapshot validation failure

No runtime mutation:

- Eligibility decides only
- eligibility validation and decision creation must not mutate input or runtime state
- eligibility must not read or write files, stores, journals, audit logs, scheduler queues, operator state, or execution state

No execution:

- Eligibility must not execute runtime
- eligibility must not call `resume(...)`, `execute_resume(...)`, `recover(...)`, `schedule(...)`, `dispatch(...)`, or `operate(...)`

## Planning Contract

Input: eligibility decision + Runtime Snapshot Consumer public result.

Output: deterministic Resume Plan with schema `aer.runtime.resume.plan.v1`.

Required fields:

- `contract`
- `resume_token`
- `eligible`
- `status`
- `reason`
- `snapshot_id`
- `lineage`
- `consumer_status`
- `plan_steps`
- `execution_boundary`
- `metadata`
- `descriptive_only`

Optional fields:

- `operator_note`
- `blocked_reason`
- `recovery_classification`

Optional fields must be descriptive only. They must not contain runtime objects, scheduler queues, operator decisions, dispatcher calls, persistence handles, audit handles, journal handles, replay handles, recovery objects, or executable callables.

Field-level mapping table:

| Source field | Resume Plan field | Required / Optional | Mapping rule | Invalid-input behavior |
| --- | --- | --- | --- | --- |
| eligibility `contract` | `contract` | Required | Output contract is always `aer.runtime.resume.plan.v1`; input eligibility must be `aer.runtime.resume.eligibility.v1`. | Planning Error or Compatibility Error. |
| eligibility + consumer result | `resume_token` | Required | Deterministic resume_token derived from canonical public eligibility fields and consumer result identity fields. | Planning Error; no token is guessed from runtime state. |
| eligibility `eligible` | `eligible` | Required | Copy descriptive eligibility boolean. | Eligibility Error. |
| eligibility `status` | `status` | Required | Copy eligibility status when plan is blocked; use planning-owned status when eligible. | Status Error. |
| eligibility `reason` | `reason` | Required | Copy descriptive reason or use `None` for eligible plan. | Eligibility Error. |
| consumer result `snapshot_id` | `snapshot_id` | Required | Preserve Snapshot Consumer public result identity. | Identity Error. |
| consumer result `lineage` | `lineage` | Required | Preserve Snapshot Consumer public result lineage. | Lineage Error. |
| consumer result `status` | `consumer_status` | Required | Preserve consumer public status as source evidence. | Consumer Result Error. |
| eligibility decision | `plan_steps` | Required | Produce descriptive plan steps only, such as `verify_identity` and `prepare_resume_handoff`. | Planning Error. |
| none | `execution_boundary` | Required | Embed an execution boundary descriptor using `aer.runtime.resume.execution_boundary.v1`; it is not execution. | Execution Boundary Error. |
| none | `metadata` | Required | Resume-owned metadata; default empty mapping. | Planning Error if not a mapping. |
| none | `descriptive_only` | Required | Always true. | Safety Error if false. |
| optional descriptive source | `operator_note` | Optional | Descriptive operator-facing note only. | Safety Error if executable or stateful. |
| eligibility `reason` | `blocked_reason` | Optional | Descriptive blocked reason when plan is not eligible. | Eligibility Error. |
| eligibility `status` | `recovery_classification` | Optional | Descriptive classification when status is `recovery_required`; recovery remains future-domain. | Safety Error if recovery is performed. |
| any unlisted field | any unlisted Resume Plan field | Prohibited | Unknown fields must not be mapped, renamed, embedded, or passed through. | Compatibility Error. |

Deterministic resume_token rule:

- `resume_token` is a Resume Planning identity token, not a runtime execution token
- `resume_token` must be deterministic for equivalent public eligibility decision and consumer result identity fields
- `resume_token` must not use wall-clock time, randomness, UUID generation, filesystem state, environment state, process state, scheduler state, operator state, dispatcher state, recovery state, persistence state, audit state, journal state, replay state, or runtime execution state
- `resume_token` must not be copied from a private Snapshot, Resume Summary, Scheduler, Operator, Dispatcher, Persistence, Audit, Journal, Recovery, or execution identity

Planning plans only:

- no scheduler
- no recovery
- no operator
- no dispatcher
- no persistence
- no audit
- no journal
- no runtime execution
- no replay
- no runtime mutation

## Execution Boundary Contract

The execution boundary schema is `aer.runtime.resume.execution_boundary.v1`.

Execution is future-domain only. Package 126 does not implement execution.

A Resume Plan may be consumed later by Runtime Resume Execution only after a future package defines:

- execution-domain ownership
- execution API
- execution validation
- execution failure ownership
- scheduler and dispatcher interaction
- operator interaction, if any
- persistence, audit, and journal interaction, if any

Execution must not be hidden inside eligibility or planning. The execution must not be hidden inside eligibility or planning.

Execution Boundary required fields:

- `contract`
- `execution_allowed`
- `future_domain_only`
- `reason`

For Package 126, `execution_allowed` must be `false`, `future_domain_only` must be `true`, and `reason` must describe that execution is outside Package 126.

## Validation Contract

Validation reports are descriptive only. No auto-repair is allowed.

### Eligibility Validation

- eligibility payload must be a mapping
- `contract` must be `aer.runtime.resume.eligibility.v1`
- required eligibility fields must be present
- unknown fields are prohibited
- field values must match the Eligibility Contract type policy
- eligibility status must be in the allowed status vocabulary
- eligibility must not contain runtime objects or executable callables

### Plan Validation

- plan payload must be a mapping
- `contract` must be `aer.runtime.resume.plan.v1`
- required plan fields must be present
- optional plan fields may be omitted
- unknown fields are prohibited
- `resume_token`, `snapshot_id`, `status`, `reason`, and `consumer_status` must be strings or `None` only where the contract permits
- `lineage`, `metadata`, and `execution_boundary` must be mappings
- `plan_steps` must be descriptive values, not callables or runtime instructions
- plan validation must confirm the deterministic resume_token rule by contract, not by reading runtime state

### Execution-Boundary Validation

- execution boundary payload must be a mapping
- `contract` must be `aer.runtime.resume.execution_boundary.v1`
- required execution-boundary fields must be present
- unknown fields are prohibited
- `execution_allowed` must be `false` in Package 126
- `future_domain_only` must be `true` in Package 126
- execution-boundary validation must not execute runtime

### Unknown Field Policy

Unknown fields are prohibited for eligibility, plan, and execution boundary payloads. Unknown fields must not be ignored, renamed, embedded in metadata, persisted, audited, journaled, replayed, or passed through.

### Required Field Policy

All required fields listed in the relevant contract section must be present. Missing required fields are descriptive validation failures and must not be auto-repaired.

### Type Policy

Fields must use simple public contract values only: strings, booleans, `None`, lists of descriptive strings, and mappings of public scalar values. Runtime objects, functions, file handles, process handles, scheduler queues, operator decisions, dispatcher callables, persistence handles, audit handles, journal handles, replay handles, and recovery objects are prohibited.

### Identity Policy

Eligibility and Planning must preserve `snapshot_id` from the Runtime Snapshot Consumer public result. Planning must create only deterministic `resume_token` values from public contract data. Neither eligibility nor planning may allocate runtime session identity by reading runtime state.

### Lineage Policy

Lineage must come from the Runtime Snapshot Consumer public result. Lineage must not be recomputed from Snapshot Builder output, Snapshot private helpers, Resume Summary internals, runtime state, persistence, audit, journal, replay, recovery, scheduler, operator, or dispatcher state.

### Status Policy

Eligibility status uses Eligibility Contract vocabulary. Plan status uses Planning Contract vocabulary derived from the eligibility decision. Execution boundary status is represented only by `execution_allowed`, `future_domain_only`, and `reason` in Package 126. Status values must not trigger runtime continuation.

## Error Taxonomy

Every failure must belong to exactly one category:

| Category | Owner | Trigger condition | Auto-repair |
| --- | --- | --- | --- |
| Snapshot Error | Snapshot | Snapshot validation failure reported through the consumer result. | No |
| Consumer Result Error | Snapshot Consumer | Consumer result is malformed, missing required public fields, or not accepted as a consumer result. | No |
| Eligibility Error | Runtime Resume Eligibility | Eligibility payload or decision is invalid apart from identity, lineage, status, compatibility, or safety errors. | No |
| Planning Error | Runtime Resume Planning | Resume Plan payload or planning input is invalid apart from identity, lineage, status, compatibility, execution-boundary, or safety errors. | No |
| Execution Boundary Error | Future Runtime Resume Execution | Execution boundary payload is malformed or attempts to enable execution in Package 126. | No |
| Identity Error | Runtime Resume | `snapshot_id` or `resume_token` identity is missing, malformed, non-deterministic, or copied from a prohibited source. | No |
| Lineage Error | Runtime Resume | Lineage is missing, malformed, mismatched, recomputed from prohibited sources, or exposes private upstream data. | No |
| Status Error | Runtime Resume | Status is outside the contract vocabulary or attempts to trigger runtime continuation. | No |
| Safety Error | Runtime Resume | Payload attempts mutation, recovery, scheduling, operator call, dispatch, persistence, audit, journal, replay, or runtime execution. | No |
| Compatibility Error | Runtime Resume | Contract value is missing, unsupported, silently upgraded, silently downgraded, or accepts future schema versions without a migration contract. | No |

Validation reports are descriptive only. No auto-repair.

## Responsibility Matrix

Exactly one owner per capability:

| Capability | Owner | Contract responsibility |
| --- | --- | --- |
| Snapshot validation | Snapshot | Owns Snapshot validation and validation error vocabulary. |
| Snapshot consumer result | Snapshot Consumer | Owns public consumer result shape and acceptance result. |
| Resume eligibility | Runtime Resume Eligibility | Owns descriptive eligibility decision only. |
| Resume planning | Runtime Resume Planning | Owns deterministic Resume Plan creation only. |
| Resume execution | Future Runtime Resume Execution | Owns future execution outside Package 126. |
| Recovery | Runtime Recovery | Owns recovery behavior; Resume may only classify recovery-required descriptively. |
| Scheduler | Scheduler | Owns scheduling and continuation. |
| Operator | Operator | Owns operator decisions and approval flow. |
| Dispatcher | Dispatcher | Owns execution routing. |
| Persistence | Persistence | Owns durable storage. |
| Audit | Audit | Owns audit reporting and readback. |
| Journal | Journal | Owns journal emission and replay surfaces. |

No shared ownership is allowed.

## Public API Contract

Future implementation may expose only:

- `check_resume_eligibility(...)`
- `build_resume_plan(...)`
- `validate_resume_plan(...)`
- `resume_plan_to_summary(...)`

These APIs preserve the responsibility split:

- `check_resume_eligibility(...)` decides only
- `build_resume_plan(...)` plans only
- `validate_resume_plan(...)` validates only
- `resume_plan_to_summary(...)` projects only

Do not expose:

- `resume(...)`
- `execute_resume(...)`
- `recover(...)`
- `schedule(...)`
- `dispatch(...)`
- `operate(...)`

Forbidden public APIs are rejected by this contract text because they imply execution, recovery, scheduling, dispatch, or operator behavior.

## Architecture Rules

- Resume Contract consumes Snapshot Consumer public result only.
- Resume Contract must not call Snapshot Builder directly.
- Resume Contract must not duplicate Snapshot validation logic.
- Resume Contract must not perform Recovery.
- Resume Contract must not schedule.
- Resume Contract must not dispatch.
- Resume Contract must not call Operator.
- Resume Contract must not persist, audit, journal, replay, or execute.
- Eligibility decides only.
- Planning plans only.
- Execution is future-domain only.
- No piecemeal architecture patches.
- Runtime execution remains forbidden in Package 126.

## GO / NO-GO

GO means Runtime Resume contract is complete enough to begin implementation of Eligibility and Planning in the next package.

NO-GO means implementation is blocked and missing architecture must be resolved by one complete contract package, not piecemeal patches.

Runtime Resume contract is complete enough to begin implementation of Eligibility and Planning in Package 127.

Final decision: GO
