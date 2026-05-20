# Patch / Diff Apply Flow

Date: 2026-05-20

This document characterizes the first Codex-like engineering workflow layer above the sealed L4 Runtime Mainline. It is documentation only. It does not enable unrestricted autonomous patch apply, introduce a production patch engine, modify `scheduler.py`, modify `system_boot.py`, or weaken freeze contracts.

## Boundary

Patch / diff apply is an upper engineering workflow, not a new runtime authority surface.

The workflow may scan the repository, propose impacted files, prepare a diff, and request review. A patch is canonical only when it enters the existing governed repair / mutation / runtime spine and returns sealed evidence, audit metadata, verification, and rollback/recovery eligibility.

The current invariants still hold:

- runtime owns execution authority;
- self-edit success requires governed repair, mutation, and runtime lineage;
- unrestricted autonomous mutation is disabled;
- scheduler remains compatibility and orchestration only;
- `system_boot.py` remains bootstrap only.

## Intended Flow

The intended Codex-like flow is:

```text
repo scan
 -> impacted file plan
 -> proposed diff
 -> approval/authority gate
 -> governed mutation request
 -> apply transaction
 -> verification command
 -> sealed evidence/audit
 -> rollback/recovery eligibility
```

Meaning of each stage:

- `repo scan`: read-only inspection of files, tests, ownership boundaries, and existing contracts.
- `impacted file plan`: read-only plan of files, risk, allowed roots, denied paths, expected verification, and rollback expectations.
- `proposed diff`: proposed patch data or replacement content. This is not a mutation and must not be treated as applied.
- `approval/authority gate`: review, capability, scope, and authority checks before mutation can become executable.
- `governed mutation request`: conversion into a committed repair transaction and governed mutation request.
- `apply transaction`: runtime-owned patch plan and apply through the mutation runtime pipeline.
- `verification command`: targeted or full verification selected by risk; success cannot be recorded without a verification result.
- `sealed evidence/audit`: runtime evidence id, evidence record, and audit metadata tied to the mutation transaction and request.
- `rollback/recovery eligibility`: rollback-ready mutation artifacts and recovery eligibility over governed lineage.

## Existing Components

Existing components already support parts of this shape:

- `core.runtime.repair_transaction_execution_bridge` converts committed repair transactions into executable mutation operations and normalizes `patch` / `apply_patch` actions into `patch_file`.
- `core.runtime.repair_transaction_gateway_adapter` builds governed mutation gateway requests with allowed/denied paths, mutation request id, replay id, audit id, authorization, scope gate, and repair authority governance metadata.
- `core.runtime.mutation_runtime_pipeline` owns patch plan creation, verification, approval, controlled apply, audit writing, result writing, and canonical runtime evidence.
- `core.runtime.mutation_patch_apply` owns the low-level patch plan and apply mechanics inside the runtime pipeline, including path normalization, scope checks, sandbox materialization, rollback paths, and report writing.
- `core.runtime.mutation_verification` owns verification result shape and enforcement.
- `core.runtime.mutation_approval` owns approval evaluation and enforcement.
- `core.runtime.mutation_audit` owns mutation audit records and audit events.
- `core.runtime.runtime_evidence_chain` owns canonical runtime evidence validation.
- `core.runtime.repair_rollback`, `core.runtime.rollback_verification`, and recovery modules support rollback and recovery characterization, but do not make raw patch apply recoverable by themselves.

These are runtime internals or governed entry points. The patch / diff workflow must not expose their internals as a broad public patch API.

## Required Gates

A patch / diff apply result is canonical only if all gates are represented:

- read-only plan gate: repo scan and impacted file plan are non-mutating;
- authority gate: runtime identity, authority scope, capability scope, authorization, and scope gate are present where applicable;
- scope gate: allowed roots, denied paths, max changed files, new-file permission, and delete permission are explicit;
- repair transaction gate: mutation comes through a committed runtime repair transaction or a future wrapper with equivalent lineage;
- mutation request gate: mutation transaction id and mutation request id are preserved;
- verification gate: verification result is present and passed;
- approval gate: approval mode and approval result are present;
- rollback gate: rollback eligibility or rollback-ready state is present before success;
- evidence gate: runtime evidence id and canonical evidence record are present;
- audit gate: runtime audit metadata and mutation audit record preserve evidence and lineage;
- recovery gate: recovery eligibility requires governed lineage and must reject raw or incomplete lineage.

## Required Evidence And Audit Fields

Canonical patch / diff success must preserve:

- `plan_id`;
- `diff_id`;
- authority metadata;
- runtime evidence id;
- runtime evidence record;
- runtime audit metadata;
- repair transaction id or mutation transaction id;
- mutation request id;
- replay session id or replay id;
- audit id;
- task id and proposal id where applicable;
- patch plan reference or patch plan metadata;
- approval result;
- verification result;
- apply transaction result;
- rollback eligibility marker;
- recovery eligibility marker.

Missing authority metadata, runtime evidence id, audit metadata, mutation/repair lineage, verification result, or rollback/recovery eligibility means the result is not canonical patch / diff apply success.

## Rollback And Recovery Expectations

Rollback and recovery are runtime-owned outcomes, not patch planner promises.

Expected behavior:

- proposed diffs are reversible only as proposals until runtime apply creates rollback artifacts;
- runtime apply must record rollback readiness or rollback paths as applicable;
- recovery eligibility requires governed evidence, audit, replay, mutation request, and repair or mutation transaction lineage;
- raw file writes, direct patch application, or subprocess-driven patching are not recoverable as governed patch / diff success;
- dry-run patch planning may report risk and expected verification but must not claim rollback/recovery eligibility.

## Forbidden Bypasses

The patch / diff workflow must not:

- write files directly as a substitute for governed mutation;
- call `apply_patch_plan` directly from an upper layer;
- call patch apply primitives directly from Codex, planner, agent, UI, plugin, scheduler, or bootstrap code;
- call scheduler private methods to apply or enqueue patch mutation;
- use raw subprocess patching as canonical success;
- emit or forge runtime evidence directly;
- skip approval, scope, verification, rollback, evidence, or audit gates;
- treat a proposed diff as applied;
- treat a dry-run result as executable success;
- modify `scheduler.py` or `system_boot.py` as part of patch flow enablement;
- broaden production mutation behavior without dedicated tests and review.

## Safe Extension Surfaces

Safe near-term surfaces are non-invasive:

- documentation and contract tests;
- read-only repo scan summaries;
- read-only impacted file plans;
- read-only proposed diff records;
- review artifacts that do not mutate;
- policy and authority reports that block or require approval;
- wrappers that delegate to the existing governed repair / mutation / runtime spine and preserve metadata;
- verification profile declarations;
- rollback/recovery eligibility reports over existing governed evidence.

## Deferred Implementation Steps

Future production enablement is deferred until these pieces are explicit:

- public patch / diff request wrapper;
- stable impacted file plan schema;
- stable proposed diff schema with diff id;
- approval and authority contract for patch apply;
- scope contract for allowed roots, denied paths, deletes, and max file count;
- verification profile mapping by risk;
- runtime wrapper that converts an approved diff into a governed repair transaction;
- rollback/recovery eligibility report over sealed evidence;
- operator review artifact for sensitive runtime files;
- regression suite for freeze, topology, self-edit gate, mutation governance, repair transaction, evidence, rollback, recovery, and scheduler compatibility.

## Required Tests Before Future Production Enablement

Before any broad production patch apply feature is enabled, the following classes of tests must pass:

- L4 runtime mainline freeze contract;
- runtime topology freeze gate;
- governed self-edit gate contract;
- patch / diff apply flow contract;
- repair transaction to governed execution;
- mutation governance and mutation bypass enforcement;
- runtime mutation authority boundaries;
- recovery, replay, evidence, audit, and seal contracts;
- scheduler compatibility and boundary import contracts;
- focused wrapper tests for any new public patch / diff request surface.

## Non-Goals

This document does not:

- implement a production patch engine;
- enable autonomous patch apply;
- bypass governed repair transactions;
- bypass the mutation runtime pipeline;
- bypass runtime evidence or audit;
- change runtime behavior;
- refactor scheduler;
- modify bootstrap wiring;
- approve raw file writes;
- approve raw subprocess patching;
- make direct patch apply a public API.
