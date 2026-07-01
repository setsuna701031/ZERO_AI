# Runtime Snapshot Integration Blueprint

## Purpose

Package 122 defines the complete Runtime Snapshot Integration domain before any runtime integration code is modified.

Runtime consumes Snapshot because Snapshot v1 is the sealed, deterministic boundary between Resume Summary and future runtime consumers. Snapshot solves these problems:

- gives Runtime Integration a stable public payload instead of a Resume Summary implementation object
- provides deterministic `snapshot_id` identity for integration correlation
- validates Snapshot payloads before runtime consumers act on them
- prevents Resume, Recovery, Scheduler, Operator, Dispatcher, Persistence, Audit, and Journal concerns from leaking into Snapshot
- gives future integration packages one architectural source rather than patch-driven local decisions

Runtime remains responsible for consuming validated Snapshot payloads, deciding when they are used, routing them through runtime integration, coordinating resume and recovery behavior, dispatching execution, and connecting future persistence, audit, and journal surfaces.

This package is documentation + seal only. It does not implement runtime integration, modify runtime behavior, modify Snapshot Builder, modify Snapshot Validator, modify Scheduler, modify Recovery, modify Dispatcher, modify Operator, add persistence, add replay, add audit, add journal, weaken previous seals, or invent implementation details.

## Domain Boundary

### Snapshot Domain

Snapshot owns only Snapshot v1 public payload construction, validation, summary projection, deterministic `snapshot_id` generation, and Snapshot-owned error vocabulary. Snapshot remains independent and must not import Runtime Integration, Runtime Resume, Runtime Recovery, Scheduler, Operator, Persistence, Audit, Journal, Runtime Dispatcher, or Work Package Runtime behavior.

### Runtime Integration Domain

Runtime Integration owns the first runtime consumer of validated Snapshot v1 payloads and the orchestration boundary that decides whether a Snapshot may be presented to Resume, Recovery, Scheduler, Operator, Dispatcher, Persistence, Audit, Journal, or Work Package Runtime packages.

Runtime Integration does not own Snapshot Builder, Snapshot Validator, or Resume Summary vocabulary.

### Recovery Domain

Recovery owns recovery planning and recovery execution behavior after Runtime Integration has accepted a Snapshot. Recovery may consume Snapshot-derived integration records only through a future explicit integration API. Recovery does not validate raw Snapshot payloads directly unless a future package grants that boundary.

### Scheduler

Scheduler owns scheduling decisions, queue timing, prioritization, and future scheduled use of Snapshot-derived runtime integration records. Scheduler does not build Snapshot payloads, validate Snapshot identity, or mutate Snapshot data.

### Operator

Operator owns operator loop decisions, human-facing runtime interpretation, approval flow coordination, and operator-level response to Snapshot-derived state. Operator does not absorb Snapshot validation or persistence responsibilities.

### Persistence

Persistence owns durable storage if a future package stores Snapshot-derived integration state. Persistence must not become part of Snapshot v1, and Snapshot must not write to storage.

### Audit

Audit owns audit reporting and readback if a future package emits or reads Snapshot-related audit evidence. Audit must consume explicit integration records, not raw private Runtime or Snapshot internals.

### Journal

Journal owns event or journal emission if a future package records Snapshot integration events. Journal must not be required for Snapshot Builder or Snapshot Validator behavior.

### Dispatcher

Runtime Dispatcher owns execution routing after Runtime Integration authorizes dispatch. Dispatcher does not validate Snapshot payloads directly and does not own Snapshot identity.

### Work Package Runtime

Work Package Runtime owns package execution context and any future package-level consumption of Snapshot-derived integration state. It must not bypass Runtime Integration or call Snapshot as an execution shortcut.

## Responsibility Matrix

Every capability has exactly one owning domain. No shared ownership is allowed.

| Capability | Owning domain | Responsibility |
| --- | --- | --- |
| Resume Summary | Resume Summary | Owns Resume Summary v1 projection, fields, status, outcome, and reason vocabulary. |
| Snapshot Builder | Snapshot | Builds Snapshot v1 payloads from Resume Summary v1 public fields only. |
| Snapshot Validator | Snapshot | Validates Snapshot v1 payloads and returns descriptive-only validation reports. |
| Runtime Snapshot Consumer | Runtime Integration | Consumes validated Snapshot v1 payloads and creates future integration records. |
| Runtime Resume | Runtime Integration | Coordinates future runtime resume behavior that uses Snapshot-derived integration records. |
| Runtime Recovery | Runtime Integration | Coordinates future recovery behavior that uses Snapshot-derived integration records. |
| Scheduler | Runtime Integration | Coordinates future scheduler-facing Snapshot integration through explicit integration records. |
| Operator | Runtime Integration | Coordinates future operator-facing Snapshot integration through explicit integration records. |
| Persistence | Runtime Integration | Coordinates future persistence boundary for Snapshot-derived integration records. |
| Audit | Runtime Integration | Coordinates future audit boundary for Snapshot-derived integration records. |
| Journal | Runtime Integration | Coordinates future journal boundary for Snapshot-derived integration records. |
| Runtime Dispatcher | Runtime Integration | Coordinates future dispatcher and execution routing boundary. |
| Work Package Runtime | Runtime Integration | Coordinates future work-package runtime use of Snapshot-derived integration records. |

Snapshot shall not absorb responsibilities owned by Runtime Integration.

This matrix is the architectural boundary for all future Runtime Snapshot integration packages.

## Single Source of Domain Logic

Runtime Integration may orchestrate domain boundaries, but it shall not duplicate, reimplement, or replace domain logic.

The owning domain remains the single source for its own rules:

- Integration layer may orchestrate.
- Integration layer shall not duplicate Domain logic.
- Domain rules must remain owned by the Domain.
- Integration layer consumes Domain public APIs only.
- Any new Domain behavior must be added in the owning Domain, not in the Integration layer.

Runtime Integration may call Snapshot public APIs such as `validate_snapshot(...)` and consume their public outputs. Runtime Integration must not compute Snapshot identity, validate Snapshot structure independently, repair Snapshot payloads, build Snapshot payloads, or recreate Snapshot-owned status, lineage, validation, or error-taxonomy rules.

This rule applies to every future Runtime Integration package, not only Runtime Snapshot Consumer.

## Runtime Lifecycle

The complete lifecycle is:

1. Resume Summary
   Resume Summary v1 produces the public input payload that Snapshot Builder may consume. Runtime Integration must not consume Resume Marker internals as a shortcut.

2. Snapshot Build
   Snapshot Builder creates a Snapshot v1 payload from Resume Summary v1 public fields. This remains inside Snapshot Domain.

3. Snapshot Validation
   Snapshot Validator validates the Snapshot v1 payload before any runtime consumer acts. Validation failure belongs to Snapshot Domain.

4. Snapshot Accepted
   Runtime Integration may accept only a Snapshot payload that passes Snapshot validation. Acceptance does not execute, schedule, persist, audit, journal, recover, resume, or dispatch by itself.

5. Runtime Integration
   Runtime Integration converts the accepted Snapshot payload into a future integration record or handoff defined by a later package. This is the first Runtime Integration-owned boundary.

6. Resume
   Runtime Resume may consume the integration record when a future Resume Integration package explicitly defines that API.

7. Recovery
   Runtime Recovery may consume the integration record when a future Recovery Integration package explicitly defines that API.

8. Scheduling and Operator Coordination
   Scheduler and Operator may consume integration records only through future explicit APIs. They must not call Snapshot Builder or Validator as hidden runtime dependencies.

9. Dispatcher and Execution
   Runtime Dispatcher may route execution only after future integration packages define acceptance, failure handling, and ownership. Dispatcher failure belongs to Runtime Integration.

10. Persistence, Audit, and Journal
    Future Persistence, Audit, and Journal packages may persist, report, or journal Snapshot-derived integration records only through explicit contracts. They do not become Snapshot dependencies.

11. Next Snapshot
    After execution or recovery produces a new Resume Summary boundary, Snapshot Builder may create the next Snapshot. The next Snapshot is a new Snapshot-owned payload, not mutation of the prior Snapshot.

Each transition must have one owner and one explicit API. Hidden calls, circular ownership, and pass-through of private objects are forbidden.

## Integration API

This blueprint defines public integration surfaces to be implemented by future packages. It does not implement them.

| Surface | Allowed input | Allowed output | Allowed caller | Allowed callee | Forbidden caller | Forbidden callee |
| --- | --- | --- | --- | --- | --- | --- |
| Runtime Snapshot Consumer | validated Snapshot v1 public payload | Runtime Integration acceptance result | Runtime Integration package entrypoint | Snapshot Validator for validation report only | Scheduler, Operator, Dispatcher, Persistence, Audit, Journal, Work Package Runtime | Runtime mainline, Scheduler, Operator, Dispatcher, Persistence, Audit, Journal |
| Resume Integration | Runtime Integration acceptance result | Resume handoff result | Runtime Integration | Runtime Resume boundary | Snapshot Builder, Snapshot Validator, Scheduler, Operator | Snapshot private helpers, Resume Marker internals |
| Recovery Integration | Runtime Integration acceptance or resume failure result | Recovery handoff result | Runtime Integration | Runtime Recovery boundary | Snapshot Builder, Snapshot Validator, Scheduler, Operator | Snapshot private helpers, Recovery internals |
| Scheduler Integration | Runtime Integration scheduling handoff | Scheduling result | Runtime Integration | Scheduler boundary | Snapshot Domain, Persistence, Audit, Journal | Snapshot private helpers |
| Operator Integration | Runtime Integration operator handoff | Operator decision result | Runtime Integration | Operator boundary | Snapshot Domain, Persistence, Audit, Journal | Snapshot private helpers |
| Dispatcher Integration | Runtime Integration dispatch handoff | Dispatch result | Runtime Integration | Runtime Dispatcher boundary | Snapshot Domain, Scheduler direct calls | Snapshot private helpers |
| Persistence Integration | Runtime Integration persistence record | Persistence result | Runtime Integration | Persistence boundary | Snapshot Domain, Scheduler, Operator | Snapshot private helpers |
| Audit Integration | Runtime Integration audit record | Audit result | Runtime Integration | Audit boundary | Snapshot Domain, Scheduler, Operator | Snapshot private helpers |
| Journal Integration | Runtime Integration journal record | Journal result | Runtime Integration | Journal boundary | Snapshot Domain, Scheduler, Operator | Snapshot private helpers |
| Work Package Runtime Integration | Runtime Integration work-package handoff | Work-package runtime result | Runtime Integration | Work Package Runtime boundary | Snapshot Domain, Scheduler direct calls | Snapshot private helpers |

Allowed inputs are Snapshot v1 public payloads or Runtime Integration-owned records derived from them. Allowed outputs are Runtime Integration-owned results or domain-specific handoffs defined by future packages. Forbidden callers and callees prevent direct runtime shortcuts around Runtime Integration.

## Dependency Rules

Allowed dependencies:

- Runtime Integration may import Snapshot public API: `validate_snapshot(...)`, `snapshot_to_summary(...)`, and approved Snapshot constants when a future package explicitly implements that boundary.
- Runtime Integration may receive Snapshot v1 public payloads.
- Future integration packages may depend on earlier Runtime Integration contracts defined by this blueprint.
- Domain packages may consume Runtime Integration-owned handoffs that are explicitly defined for them.

Forbidden dependencies:

- Snapshot must not depend on Runtime Integration.
- Snapshot must not depend on Runtime Resume, Runtime Recovery, Scheduler, Operator, Persistence, Audit, Journal, Runtime Dispatcher, Work Package Runtime, runtime mainline, task runner, event log, filesystem, environment, process state, time, random, or `uuid4`.
- Scheduler, Operator, Dispatcher, Persistence, Audit, Journal, and Work Package Runtime must not bypass Runtime Integration to call Snapshot private helpers.
- Runtime Integration must not import Snapshot private helpers.
- Runtime Integration must not mutate Snapshot payloads.
- Runtime Integration must not make Snapshot responsible for resume, recovery, dispatch, scheduling, persistence, audit, journal, or work-package runtime execution.

No circular dependency rule:

- Snapshot points to no runtime integration domain.
- Runtime Integration may point to Snapshot public API only.
- Domain integrations point to Runtime Integration-owned handoffs, not back into Snapshot.
- No future package may add a cycle from Snapshot to Runtime Integration or from domain integration back into Snapshot private behavior.

Snapshot remains independent.

## Failure Boundary

Every failure belongs to exactly one owner.

| Failure | Owning domain | Required handling |
| --- | --- | --- |
| Validation failure | Snapshot | Return descriptive-only validation report; no repair, no runtime action. |
| Integration failure | Runtime Integration | Reject or stop the integration handoff in a future Runtime Integration result. |
| Resume failure | Runtime Integration | Route to future Resume Integration failure handling; do not mutate Snapshot. |
| Recovery failure | Runtime Integration | Route to future Recovery Integration failure handling; do not mutate Snapshot. |
| Dispatcher failure | Runtime Integration | Report dispatch failure through future Dispatcher Integration result. |
| Ownership violation | Runtime Integration | Reject the integration route and report the violated owner boundary. |

Failure reports must not silently repair Snapshot payloads, reassign ownership, or continue through a different domain without an explicit future contract.

## Evolution Strategy

Future:

- Future packages implement the roadmap in this blueprint in order.
- Each package must define its own integration contract before modifying runtime behavior.
- Any package that discovers a missing architecture item must stop and create one complete architecture package instead of piecemeal patches.

v2:

- Snapshot v1 remains the compatibility boundary for current Runtime Snapshot integration.
- Snapshot v2 requires a dedicated v2 Snapshot contract before any v2 implementation or integration.
- Runtime Integration v2 migration must accept only explicitly versioned payloads.

v3:

- Snapshot v3 or Runtime Integration v3 must define a separate migration plan, compatibility policy, and deprecation path.
- v3 must not silently reinterpret v1 or v2 payloads.

Migration boundary:

- Migration belongs to Runtime Integration unless it changes Snapshot payload construction or validation, in which case a new Snapshot contract is required first.

Compatibility boundary:

- Compatibility is by explicit `contract` value and public fields only.
- Unknown fields, private objects, wrapper keys, and implementation diagnostics are not compatibility surfaces.

Deprecation strategy:

- Deprecation must be contract-led, package-scoped, tested, and documented before runtime behavior changes.
- Deprecation must preserve v1 validation behavior until a future package explicitly retires it.

## Package Plan

### Package 123: Runtime Snapshot Consumer

Goal: implement the first Runtime Integration-owned consumer of validated Snapshot v1 public payloads.

Inputs: Snapshot v1 public payload, Snapshot validation report.

Outputs: Runtime Integration acceptance result.

Dependencies: Package 122 blueprint, Snapshot public API, Package 121 GO decision.

Acceptance criteria: accepts only valid Snapshot v1 payloads, rejects invalid payloads descriptively, does not resume, recover, schedule, dispatch, persist, audit, journal, or execute.

### Package 124: Resume Integration

Goal: connect Runtime Snapshot Consumer acceptance result to Runtime Resume boundary.

Inputs: Runtime Integration acceptance result.

Outputs: Resume handoff result.

Dependencies: Package 123 acceptance result contract.

Acceptance criteria: no Snapshot private helper use, no direct Resume Marker internals, no recovery or dispatch behavior.

### Package 125: Recovery Integration

Goal: connect Runtime Integration resume or acceptance outcomes to Runtime Recovery boundary.

Inputs: Runtime Integration acceptance result and future resume failure result.

Outputs: Recovery handoff result.

Dependencies: Package 124 resume integration boundary.

Acceptance criteria: recovery ownership remains Runtime Integration, Snapshot is not mutated, and no scheduler/operator/dispatcher behavior is added.

### Package 126: Scheduler Integration

Goal: define scheduler-facing use of Runtime Integration handoffs.

Inputs: Runtime Integration scheduling handoff.

Outputs: Scheduling result.

Dependencies: Package 123 through Package 125 integration records.

Acceptance criteria: Scheduler does not call Snapshot directly and cannot bypass Runtime Integration.

### Package 127: Operator Integration

Goal: define operator-facing use of Runtime Integration handoffs.

Inputs: Runtime Integration operator handoff.

Outputs: Operator decision result.

Dependencies: Package 126 scheduler integration where relevant.

Acceptance criteria: Operator does not own Snapshot validation, persistence, recovery, or dispatch.

### Package 128: Dispatcher Integration

Goal: define dispatcher-facing execution routing from Runtime Integration handoffs.

Inputs: Runtime Integration dispatch handoff.

Outputs: Dispatch result.

Dependencies: Package 123 through Package 127 integration contracts.

Acceptance criteria: dispatch occurs only through explicit Runtime Integration authorization and does not mutate Snapshot payloads.

### Package 129: Runtime Mainline Landing

Goal: land the integrated Runtime Snapshot path into the runtime mainline after consumer, resume, recovery, scheduler, operator, and dispatcher boundaries are sealed.

Inputs: sealed integration contracts and results from Package 123 through Package 128.

Outputs: runtime mainline integration result.

Dependencies: all prior Runtime Snapshot integration packages.

Acceptance criteria: no hidden dependencies, no circular dependency, no Snapshot scope expansion, and all failure ownership remains single-owner.

### Package 130: Integration Closure Review

Goal: review Runtime Snapshot integration after mainline landing.

Inputs: all integration contracts, tests, and mainline landing evidence.

Outputs: GO / NO-GO closure decision for the Runtime Snapshot integration domain.

Dependencies: Package 129 runtime mainline landing.

Acceptance criteria: verifies architecture compliance, no responsibility drift, no patch-driven architecture, no hidden dependency, and no future migration breakage.

## Architecture Risks

Patch-driven architecture:

- Avoided by making this blueprint the single architectural source before implementation packages begin.

Responsibility drift:

- Avoided by the Responsibility Matrix and exactly-one-owner failure boundary.

Hidden dependency:

- Avoided by explicit allowed and forbidden dependencies plus Integration API tables.

Circular dependency:

- Avoided by keeping Snapshot independent and requiring domain packages to consume Runtime Integration handoffs.

Runtime leakage:

- Avoided by forbidding Scheduler, Operator, Dispatcher, Persistence, Audit, Journal, and Work Package Runtime from calling Snapshot private helpers or bypassing Runtime Integration.

Snapshot scope expansion:

- Avoided by stating that Snapshot shall not absorb responsibilities owned by Runtime Integration.

Integration shortcut:

- Avoided by the package roadmap, where each domain boundary is implemented and sealed in sequence.

Future migration breakage:

- Avoided by explicit v2/v3 contract boundaries, migration rules, compatibility boundaries, and deprecation strategy.

## GO / NO-GO

GO means Runtime Integration architecture is complete enough to begin implementation packages.

NO-GO means implementation is blocked. Missing architecture must be solved by one complete architecture package, never by piecemeal patches.

Runtime Snapshot Integration architecture is complete enough to begin implementation packages starting with Package 123: Runtime Snapshot Consumer.

Final decision: GO
