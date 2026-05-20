# Governed Self-Edit Upper Layer

Date: 2026-05-20

This document characterizes the governed self-edit upper layer on top of the sealed L4 Runtime Mainline. It is documentation only. It does not enable unrestricted autonomous mutation, change runtime behavior, refactor `scheduler.py`, modify `system_boot.py`, or weaken the runtime freeze contracts.

## Current Sealed Runtime Kernel

The sealed L4 Runtime Mainline owns execution authority, evidence, audit, replay, repair, recovery, and topology freeze contracts.

Current kernel invariants:

- `core.runtime.executor` owns governed command and subprocess execution.
- Governed execution emits canonical runtime evidence and audit metadata.
- Side-effect records preserve runtime evidence and audit metadata.
- Repair and mutation preserve mutation transaction, mutation request, evidence, audit, and replay lineage.
- Recovery verification requires governed evidence, audit, authority, execution session, replay session, mutation, repair, and raw-execution guard lineage.
- Replay, continuation, and cross-session handoff preserve source execution and replay session lineage.
- `scheduler.py` remains compatibility, queue, and orchestration surface only.
- `services/system_boot.py` remains bootstrap wiring for owners and evidence adapters only.

The current runtime kernel is therefore not a place for autonomous self-edit policy to accumulate. Self-edit may request work, describe intent, and prepare reviewed proposals, but execution and repository mutation must remain behind the governed runtime and repair transaction topology.

## Future Self-Edit Upper Layer

The self-edit upper layer is a governed control plane above the sealed kernel. It may assemble evidence, describe intent, produce plans, request review, and pass an approved repair transaction into the runtime-owned mutation path.

The characterized flow is:

```text
intent
 -> planning
 -> governed repair transaction
 -> mutation request
 -> governed execution
 -> sealed evidence
 -> verification
 -> replay/recovery eligibility
 -> rollback eligibility
```

Meaning of each stage:

- `intent`: captures the operator or system goal, source context, risk, scope, and reason for considering a self-edit.
- `planning`: produces read-only proposals and compatibility checks. Planning does not mutate files, enqueue scheduler work, emit runtime evidence directly, or approve itself.
- `governed repair transaction`: converts an approved change into the runtime repair transaction lifecycle through `create_runtime_repair_transaction`, `stage_runtime_repair_mutation`, and `commit_runtime_repair_transaction`.
- `mutation request`: bridges the committed transaction through `execute_committed_runtime_repair_transaction`, `execute_governed_repair_transaction`, and `repair_transaction_gateway_adapter`.
- `governed execution`: runs through the governed mutation gateway and `run_mutation_runtime_pipeline`, where scope validation, verification, approval, rollback readiness, patch apply, and audit are runtime-owned.
- `sealed evidence`: records canonical runtime evidence and audit metadata, including execution session, replay session, mutation transaction, mutation request, authority metadata, and audit lineage.
- `verification`: proves the patch plan and execution result satisfy the selected verification requirement before success is recorded.
- `replay/recovery eligibility`: depends on preserved governed lineage and sealed evidence. Recovery verification must reject raw or incomplete lineage.
- `rollback eligibility`: depends on rollback-ready mutation execution artifacts and runtime-owned rollback records, not on planner promises.

## Safe Mutation Boundaries

Safe extension surfaces are additive and non-invasive:

- documentation that clarifies existing sealed behavior;
- read-only self-edit convergence reports such as `self_edit_mainline_convergence`;
- data-only action gateway and execution reports that keep `execute=False`, `planner_invoked=False`, and `task_enqueued=False`;
- policy, approval, and gate adapters that block or require review before mutation;
- public wrappers that delegate to existing governed runtime owners and preserve evidence metadata;
- read-only evidence, audit, replay, forensic, timeline, and handoff reports;
- narrow characterization tests that lock existing invariants without broadening authority.

Allowed upper-layer behavior:

- inspect current runtime evidence and topology;
- classify self-edit intent and risk;
- build a reviewed plan;
- request approval;
- submit an approved mutation only through the governed repair transaction path;
- report sealed evidence, verification, replay, recovery, and rollback eligibility after runtime execution.

## Forbidden Mutation Surfaces

The self-edit upper layer must not:

- call patch apply primitives directly;
- call mutation pipeline internals directly;
- call repair transaction lifecycle internals as an unreviewed shortcut;
- write workspace files outside the governed mutation gateway;
- emit or forge runtime evidence directly;
- bypass approval, scope, verification, rollback, or audit gates;
- call scheduler private methods or treat scheduler as execution authority;
- enqueue work as a substitute for governed execution authority;
- call recovery execution or verification with raw lineage;
- modify `system_boot.py` to accumulate governance execution logic;
- introduce demo-only mutation code;
- treat dry-run reports as permission to mutate;
- mutate sealed lifecycle, transaction, or evidence records after closure.

## Runtime-Owned Invariants

The upper layer must preserve these runtime-owned invariants:

- execution authority belongs to the runtime executor and governed runtime paths;
- mutation authority belongs to committed repair transactions and governed mutation execution;
- transaction authority belongs to repair transaction lifecycle and runtime transaction gates;
- evidence authority belongs to runtime evidence builders, seals, and audit metadata writers;
- recovery eligibility belongs to recovery verification over governed lineage;
- replay eligibility belongs to replay/session evidence consistency;
- rollback eligibility belongs to mutation execution artifacts and rollback-ready state;
- scheduler compatibility does not create authority;
- bootstrap wiring does not create runtime execution authority.

## Required Evidence Lineage

A self-edit mutation is eligible for replay, recovery, and rollback only when the sealed runtime result preserves:

- runtime evidence id;
- runtime audit metadata;
- execution session id;
- replay session id;
- mutation transaction id;
- mutation request id;
- repair transaction id or equivalent repair transaction lineage;
- task id and proposal id where applicable;
- authority metadata, including runtime identity, authority scope, capability scope, authorization, and scope gate state;
- verification state;
- rollback state;
- evidence seal state;
- replay consistency state.

Missing evidence, audit metadata, authority metadata, execution session, replay session, mutation transaction, mutation request, repair transaction lineage, or raw-execution guard lineage must make recovery verification ineligible.

## Rollback And Recovery Expectations

Rollback is not a planner promise. It must be grounded in runtime-owned mutation artifacts and rollback readiness.

Recovery is not a raw retry path. It must be grounded in governed evidence, replay consistency, repair lineage, and runtime recovery verification.

Expected posture:

- dry-run planning may recommend repair, replay, or review but must not execute;
- approval-required plans remain review-bound until authority is present;
- governed repair execution may be blocked by preflight, apply-plan readiness, approval, verification, recovery gate hooks, or mutation scope;
- rollback eligibility must be recorded before a repository-changing self-edit is considered complete;
- recovery verification must keep `raw_recovery_execution_allowed` false unless a future governed wrapper explicitly changes the contract with tests and docs.

## Codex Interaction Model

Codex acts as an operator-facing collaborator above the sealed kernel.

Codex may:

- inspect files, tests, evidence, and contracts;
- write documentation and narrow tests;
- propose plans and explain risk;
- make code changes when explicitly requested through normal governed development workflow;
- run compile and regression checks;
- report changed files, exact test output, and remaining risk.

Codex must not:

- claim autonomous mutation authority;
- bypass runtime repair transaction authority;
- bypass evidence or audit lineage;
- refactor scheduler as part of self-edit characterization;
- modify `system_boot.py` as part of upper-layer characterization;
- weaken freeze contracts to make a self-edit pass.

## Replay And Recovery Guarantees

The upper layer inherits guarantees from the sealed kernel only when it preserves kernel lineage.

Guaranteed when lineage is complete:

- governed execution can be tied to canonical runtime evidence;
- mutation and repair can be tied to mutation transaction and request ids;
- replay and continuation can preserve source execution and replay sessions;
- recovery verification can reject incomplete or raw lineage;
- rollback can be evaluated from runtime-owned mutation artifacts.

Not guaranteed:

- replay or recovery for ungoverned file writes;
- rollback for direct patch application outside runtime mutation artifacts;
- audit validity for evidence emitted by planners, scheduler compatibility code, or bootstrap wiring;
- autonomous mutation approval without explicit future authority gates.

## Approval And Authority Gates Before Future Autonomous Mutation

Future autonomous mutation remains deferred. Before it can be considered, the runtime needs explicit gates that are not implemented by this document:

- a reviewed autonomous intent policy with risk classification;
- a capability grant for the specific mutation scope;
- an approval chain that distinguishes dry-run, review-required, and executable mutation;
- a repair transaction authority gate that cannot be bypassed by planners or agents;
- scope gates for allowed paths, denied paths, max files changed, new files, and deletes;
- mandatory verification requirements by risk level;
- rollback readiness checks before apply;
- evidence seal validation after execution;
- replay consistency validation after execution;
- recovery eligibility validation over governed lineage;
- operator-visible audit and rollback plan for runtime-sensitive files;
- dedicated regression tests that prove scheduler, bootstrap, recovery, replay, evidence, and mutation authority boundaries remain sealed.

Until those gates exist and are sealed by tests, autonomous self-edit remains recommendation-only or review-required.

## Deferred Future Work

- Define a public governed self-edit request wrapper.
- Define a dedicated autonomous mutation approval contract.
- Define risk-specific verification profiles.
- Define operator review artifacts for self-edit proposals.
- Define a recovery wrapper if recovery execution becomes public.
- Add targeted tests for any new wrapper after it exists.
- Continue scheduler slimming only as a separate reviewed effort.
- Continue `system_boot.py` cleanup only as a separate bootstrap effort.

## Non-Goals

This document does not:

- implement autonomous mutation;
- add runtime behavior;
- change production code;
- create a new scheduler API;
- modify `scheduler.py`;
- modify `system_boot.py`;
- expose mutation internals;
- expose recovery internals;
- approve raw patch application;
- approve raw subprocess execution;
- weaken L4 Runtime Mainline freeze contracts;
- replace the governed repair transaction or mutation runtime pipeline.
