# AER Runtime Recovery Contract v1

## Purpose

Package 139 establishes the sealed public contract for the Runtime Recovery domain after Package 138 completed the Runtime Recovery Blueprint.

This contract follows the AER Domain Lifecycle Standard. It is contract-only and defines public schemas, public API names, ownership, boundaries, failure taxonomy, dependency direction, and GO / NO-GO criteria before Recovery validation or implementation begins.

Package 139 does not implement Runtime Recovery behavior, modify runtime behavior, modify core runtime modules, add scheduler behavior, add dispatcher behavior, add operator behavior, add persistence behavior, add audit behavior, add journal behavior, add replay behavior, mutate runtime state, or implement recovery execution.

## Contract Separation Rule

Runtime Recovery has three separate public contracts:

- Recovery Eligibility
- Recovery Planning
- Recovery Execution Boundary

These three public contracts must never collapse into a single API.

Recovery Eligibility decides whether a public execution consumer output is eligible for future Recovery handling.

Recovery Planning describes a recovery plan from validated eligibility.

Recovery Execution Boundary describes the edge where Recovery must stop before any future execution, scheduling, dispatch, operator, persistence, audit, journal, or replay domain takes ownership.

## Contract Evolution Policy

Recovery v1 schemas are immutable once sealed.

Breaking changes must create a new contract version, such as Recovery v2.

Old versions must not be silently overwritten.

Compatible additive changes may be proposed only through a future contract evolution package with explicit compatibility review, consumer impact review, GO / NO-GO decision, and updated compatibility matrix.

The required evolution path is:

```text
recovery_v1
↓
recovery_v2
```

Recovery must not break existing consumers by changing v1 field meaning, removing v1 fields, renaming v1 fields, changing v1 schemas, or changing v1 summary semantics in place.

## Public Schemas

### aer.runtime.recovery.eligibility.v1

Purpose: describe whether a public Runtime Resume Execution Consumer output or public execution summary is eligible for Recovery planning.

Required public fields:

- schema
- recovery_eligibility_id
- source_execution_consumer_id
- source_execution_summary_id
- eligible
- status
- failure_type
- recovery_authorized
- reasons
- metadata

Allowed status values:

- eligible
- ineligible
- invalid
- blocked

### aer.runtime.recovery.plan.v1

Purpose: describe a data-only Recovery plan derived from a valid Recovery Eligibility contract.

Required public fields:

- schema
- recovery_plan_id
- recovery_eligibility_id
- plan_status
- failure_type
- planned_actions
- downstream_requirements
- execution_boundary
- metadata

Allowed plan_status values:

- planned
- not_planned
- blocked
- invalid

### aer.runtime.recovery.execution_boundary.v1

Purpose: define where Recovery stops before future downstream execution domains begin.

Required public fields:

- schema
- recovery_plan_id
- execution_allowed
- scheduler_required
- operator_required
- persistence_required
- audit_required
- journal_required
- replay_required
- boundary_status
- metadata

Allowed boundary_status values:

- blocked
- future_domain_required
- invalid

## Public APIs

Package 139 defines these public API names as contract-only names:

- `check_recovery_eligibility(...)`
- `validate_recovery_eligibility(...)`
- `build_recovery_plan(...)`
- `validate_recovery_plan(...)`
- `recovery_eligibility_to_summary(...)`
- `recovery_plan_to_summary(...)`

No implementation is provided by Package 139.

## Ownership

Recovery owns:

- recovery eligibility
- recovery planning
- recovery failure taxonomy
- recovery public summaries

Recovery does not own:

- execution
- scheduling
- dispatch
- operator approval
- persistence
- audit
- journal
- replay

## Boundary

Recovery consumes only:

- Runtime Resume Execution Consumer public output

Recovery must never consume:

- Resume Builder internals
- Resume Planning internals
- Resume Validation internals

Recovery must not bypass the Runtime Resume Execution Consumer boundary.

## Boundary Matrix

| Domain | Direction | Allowed | Forbidden |
| --- | --- | --- | --- |
| Runtime Resume Execution Consumer | Upstream into Recovery | Public output only. | Private consumer helpers or runtime execution behavior. |
| Resume Builder | Upstream internal | None. | Builder internals or direct Recovery input. |
| Resume Planning | Upstream internal | None. | Planning internals or direct Recovery input. |
| Resume Validation | Upstream internal | None. | Validation internals or validation helper coupling. |
| Runtime Recovery | Current domain | Eligibility, planning, failure taxonomy, and public summaries as contracts. | Execution, scheduling, dispatch, operator approval, persistence, audit, journal, replay, runtime mutation. |
| Scheduler | Downstream future domain | Future requirement marker only. | Scheduling behavior or queue ownership. |
| Dispatcher | Downstream future domain | Future requirement marker only. | Dispatch behavior or command ownership. |
| Operator | Downstream future domain | Future requirement marker only. | Operator decisions or approvals. |
| Persistence | Downstream future domain | Future requirement marker only. | Persistence writes or storage ownership. |
| Audit | Downstream future domain | Future requirement marker only. | Audit emission or record ownership. |
| Journal | Downstream future domain | Future requirement marker only. | Journal events or stream ownership. |
| Replay | Downstream future domain | Future requirement marker only. | Replay behavior or token ownership. |

## Contract Compatibility Matrix

| Producer | Consumer | Compatible |
| --- | --- | --- |
| Resume Execution Consumer v1 | Recovery v1 | Yes |
| Resume Execution Consumer v2 | Recovery v1 | TBD |
| Recovery v1 | Scheduler v1 | Future |
| Recovery v1 | Persistence v1 | Future |
| Recovery v1 | Audit v1 | Future |
| Recovery v1 | Journal v1 | Future |

Compatibility entries marked TBD or Future do not authorize consumption. They require a future lifecycle package and explicit GO decision before use.

## Failure Taxonomy

Recovery defines these public failure types:

- invalid_execution_summary
- invalid_recovery_request
- recovery_not_authorized
- scheduler_required
- operator_required
- persistence_required
- audit_required
- journal_required

The taxonomy is descriptive. It does not authorize execution, scheduling, dispatch, operator approval, persistence, audit, journal, replay, or runtime mutation behavior.

## Dependency Graph

Allowed dependency direction:

```text
Resume Execution Consumer
↓
Recovery
↓
Future Scheduler
↓
Future Persistence
↓
Future Audit
↓
Future Journal
```

Recovery may not reverse-import upstream internals.

Recovery may depend only on public Runtime Resume Execution Consumer output until a future Integration Blueprint authorizes additional public handoffs.

## Lifecycle

Package 139 is the Contract phase for Runtime Recovery under the AER Domain Lifecycle Standard.

The next phase is Package 140: Runtime Recovery Validation.

Future Recovery packages must keep Eligibility, Planning, and Execution Boundary separated through Validation, Planner / Builder, Consumer Boundary, Closure Review, and Integration Blueprint phases.

## GO Criteria

Package 139 is GO only if:

- all required public schemas are defined
- Recovery Eligibility, Recovery Planning, and Recovery Execution Boundary remain separate
- public API names are contract-only
- ownership and non-ownership are explicit
- boundary rules are explicit
- Boundary Matrix is present
- Contract Evolution Policy is present
- Contract Compatibility Matrix is present
- failure taxonomy is present
- dependency graph is present
- AER Domain Lifecycle Standard is referenced
- Package 140: Runtime Recovery Validation is named as the next package

## NO-GO Criteria

Package 139 is NO-GO if:

- it implements Recovery behavior
- it modifies runtime behavior
- it modifies core runtime modules
- it collapses Eligibility, Planning, and Execution Boundary into one API
- it consumes Resume Builder, Resume Planning, or Resume Validation internals
- it authorizes execution, scheduling, dispatch, operator approval, persistence, audit, journal, replay, or runtime mutation
- it lacks a GO / NO-GO decision
- it does not name Package 140: Runtime Recovery Validation as the next package

## GO / NO-GO Decision

Final decision: GO.

AER Runtime Recovery Contract v1 is complete.

Package 139 is contract-only.

Runtime Recovery behavior is not implemented by this package.

Next package: Package 140: Runtime Recovery Validation.
