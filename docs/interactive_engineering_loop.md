# Interactive Engineering Loop

Date: 2026-05-20

This document characterizes the intended Codex-like interactive engineering loop above the sealed L4 Runtime Mainline and governed mutation spine. It is documentation only. It does not create a production autonomous agent loop, enable unrestricted editing, modify `scheduler.py`, modify `system_boot.py`, or weaken runtime freeze contracts.

## Boundary

The interactive engineering loop is an operator-facing workflow layer. It may inspect, plan, propose, request approval, submit governed mutation requests, run verification through governed execution surfaces, and summarize results.

It does not own execution authority, mutation authority, evidence authority, recovery authority, scheduler authority, or bootstrap authority.

Current invariants remain unchanged:

- runtime owns execution authority;
- self-edit success requires governed repair / mutation / runtime lineage;
- patch / diff apply is characterization-only unless routed through governed mutation;
- unrestricted autonomous mutation remains disabled;
- scheduler remains compatibility and orchestration only;
- `system_boot.py` remains bootstrap only.

## Intended Flow

The intended flow is:

```text
user task
 -> repo scan
 -> impacted file analysis
 -> execution plan
 -> diff proposal
 -> approval/authority gate
 -> governed mutation/apply transaction
 -> verification commands
 -> retry/repair loop eligibility
 -> rollback/recovery eligibility
 -> execution summary/report
```

Meaning of each stage:

- `user task`: captures the requested engineering goal, constraints, non-goals, and acceptance criteria.
- `repo scan`: read-only inspection of files, contracts, tests, ownership boundaries, and current state.
- `impacted file analysis`: read-only file set, risk, allowed roots, denied surfaces, and expected verification.
- `execution plan`: ordered non-mutating plan that separates inspection, proposal, approval, mutation, verification, and reporting.
- `diff proposal`: proposed code/content change. It is not applied and does not imply authority.
- `approval/authority gate`: human or policy approval, runtime identity, authority scope, capability scope, repair authorization, and scope gate.
- `governed mutation/apply transaction`: conversion into the governed repair transaction and mutation runtime spine.
- `verification commands`: governed command execution or recorded verification results appropriate to the risk.
- `retry/repair loop eligibility`: retry or repair may be recommended only from evidence and verification outcomes; it is not automatic mutation authority.
- `rollback/recovery eligibility`: recorded from governed mutation artifacts and sealed lineage.
- `execution summary/report`: operator-facing summary of changed files, evidence, audit, verification, rollback/recovery eligibility, and remaining risk.

## Responsibility Split

### Runtime Kernel Responsibilities

- Own command/subprocess execution authority.
- Emit sealed runtime evidence and canonical audit metadata.
- Preserve execution session, replay session, mutation transaction, mutation request, authority, and audit lineage.
- Reject recovery verification without governed lineage.
- Preserve replay, continuation, handoff, rollback, repair, and topology freeze contracts.

### Engineering Workflow Responsibilities

- Translate user tasks into an inspectable engineering workflow.
- Keep repo scan, impacted file analysis, plan, and diff proposal read-only until approved.
- Present approval needs and risk clearly.
- Submit mutation only through governed repair / mutation / runtime surfaces.
- Record verification, retry/repair eligibility, rollback/recovery eligibility, and summary.

### Planner Responsibilities

- Produce proposals, not execution authority.
- Keep mutating actions out of read-only planner proposals.
- Preserve blocked actions and reasons for auditability.
- Never call patch apply, repair transaction internals, scheduler private methods, or evidence emitters directly.

### Mutation Responsibilities

- Own mutation request normalization, scope checks, approval enforcement, verification enforcement, patch plan creation, controlled apply, rollback readiness, and mutation audit.
- Preserve mutation transaction id and mutation request id.
- Keep patch apply internals behind the governed mutation runtime pipeline.

### Approval And Authority Responsibilities

- Distinguish dry-run, review-required, and executable actions.
- Provide runtime identity, authority scope, capability scope, authorization, and scope gate metadata.
- Block missing or incomplete authority before mutation.
- Preserve approval and authority metadata in evidence and audit records.

## Safe Extension Surfaces

Safe surfaces are additive and non-invasive:

- documentation and characterization tests;
- read-only repo scan records;
- impacted file plans;
- execution plan records;
- proposed diff records;
- approval request records;
- verification profile records;
- retry/repair eligibility reports;
- rollback/recovery eligibility reports over sealed evidence;
- CLI or UI displays that request user approval without mutating;
- wrappers that delegate to existing governed runtime surfaces and preserve lineage.

## Forbidden Bypasses

The interactive engineering loop must not:

- execute shell commands directly as planner-owned execution;
- write files directly as workflow-owned mutation;
- call patch apply primitives directly;
- call mutation runtime pipeline internals directly from planner/UI/CLI code;
- call repair transaction lifecycle internals as an unreviewed shortcut;
- treat a proposed diff as applied;
- treat dry-run or planning as success;
- emit or forge runtime evidence;
- skip approval, authority, verification, audit, rollback, or recovery lineage;
- call scheduler private methods or treat scheduler as execution authority;
- modify `system_boot.py` to add engineering-loop execution authority;
- implement autonomous retry/repair mutation without future gates and tests.

## Future Retry / Repair Loop Requirements

Retry and repair remain eligibility states until future gates exist.

Future retry/repair needs:

- failure classification from sealed execution evidence;
- retry budget and stop conditions;
- repair intent and risk classification;
- approval gates before repair mutation;
- verification gates after every attempt;
- lineage across attempts, repairs, continuations, and handoffs;
- rollback/recovery eligibility after every mutating attempt;
- operator-visible report explaining why retry or repair is allowed, blocked, or review-required.

No retry/repair loop may mutate merely because verification failed.

## Future Memory And Logging Requirements

Future memory/logging surfaces must be read/query oriented until explicitly governed.

Required future records:

- user task id and plan id;
- repo scan id;
- impacted file set;
- diff proposal id;
- approval id;
- mutation transaction id and mutation request id;
- runtime evidence id;
- audit id;
- verification command/result ids;
- retry/repair eligibility id;
- rollback/recovery eligibility id;
- final execution summary id.

Memory must not become hidden authority. Logs must preserve lineage and must not rewrite sealed runtime evidence.

## Future CLI / UI Interaction Surfaces

Future CLI/UI surfaces may:

- show repo scan and impacted files;
- show execution plans and proposed diffs;
- request approval;
- show verification commands and results;
- show evidence/audit ids;
- show rollback/recovery eligibility and remaining risk.

Future CLI/UI surfaces must not:

- apply patches directly;
- run raw subprocesses as canonical execution;
- bypass approval/authority gates;
- call scheduler private methods;
- hide failed verification behind a successful summary.

## Required Canonical Workflow Shape

A canonical interactive engineering loop report must include:

- `plan_id`;
- impacted file set;
- diff proposal;
- authority approval marker;
- governed mutation lineage;
- runtime evidence id;
- runtime audit metadata;
- verification result;
- rollback eligibility;
- recovery eligibility;
- execution summary/report.

Missing approval lineage, runtime evidence, governed mutation lineage, verification, rollback/recovery eligibility, or execution summary means the result is not canonical success.

## Deferred Implementation

Deferred work:

- stable interactive engineering loop request schema;
- read-only repo scan schema;
- impacted file analysis schema;
- execution plan schema;
- diff proposal schema;
- approval/authority marker schema;
- governed mutation wrapper that delegates to existing repair/mutation/runtime spine;
- verification profile mapping;
- retry/repair loop eligibility contract;
- memory/logging records with lineage;
- CLI/UI review surfaces;
- dedicated regression suite before production enablement.

## Required Tests Before Future Production Enablement

Before enabling a production interactive engineering loop, the following must pass:

- runtime mainline freeze contract;
- runtime topology freeze gate;
- governed self-edit gate contract;
- patch / diff apply flow contract;
- interactive engineering loop contract;
- repair transaction to governed execution;
- mutation governance and mutation bypass tests;
- runtime mutation authority boundary tests;
- evidence, audit, recovery, replay, rollback, and seal tests;
- scheduler compatibility and boundary import tests;
- focused tests for any new CLI/UI or wrapper surface.

## Non-Goals

This document does not:

- create a production autonomous agent loop;
- enable unrestricted autonomous execution;
- approve planner-owned execution;
- approve raw file writes;
- approve direct patch apply;
- bypass governed repair transactions;
- bypass the mutation runtime pipeline;
- bypass runtime evidence or audit;
- modify scheduler;
- modify bootstrap wiring;
- replace the sealed runtime kernel.
