# Runtime Freeze Guardrails - Phase 4-F

Date: 2026-05-18

Source documents and tests:

- `docs/runtime_kernel_boundary_contract.md`
- `docs/runtime_mainline_freeze_audit.md`
- `tests/test_runtime_boundary_imports.py`
- `tests/test_runtime_mutation_authority_boundaries.py`

This document defines the first freeze guardrails for the ZERO Runtime Kernel. It does not implement runtime APIs, change runtime behavior, refactor `scheduler.py`, move files, or clean existing warnings.

## Protected Runtime Flows

These flows are protected by the Runtime Kernel boundary contract and freeze audit. Changes touching them require deliberate review and the protected test pack.

| Protected flow | Freeze posture | Guardrail |
| --- | --- | --- |
| Repair flow | `still_transitional` with stable governed entry candidates | Preserve governed repair entry, transaction lifecycle, review semantics, injected-step idempotency, scheduler-owned enqueue-after-injection, and replay continuation metadata. Do not expose repair transaction/apply/injection internals directly. |
| Rollback flow | `internal_only` with a narrow runtime-owned request wrapper | Rollback execution must stay in runtime/tasks ownership. Agent, planner, UI, plugins, and services may request rollback only through approved wrapper paths. Preserve Code Chain patch restore payload and reason strings. |
| Governed mutation flow | `stable_contract_candidate` at gateway level | Preserve `run_governed_mutation` request normalization, policy, approval, sandbox, patch apply, rollback, verification, evidence, and failure packaging. Mutation pipeline internals remain internal. |
| Recovery flow | `still_transitional` / `internal_only` | Recovery execution must stay internal until a governed recovery wrapper exists. Preserve recovery policy, dry-run, commit gate, approval, rollback, and evidence semantics. |
| Replay flow | read-only replay is `stable_contract_candidate`; continuation internals are `internal_only` | Read-only replay/reporting must not trigger mutation. Scheduler retry/repair replay continuation helpers must remain internal and idempotent. |
| Execution evidence flow | read/query surface is `stable_contract_candidate`; emitters are `internal_only` | Preserve evidence provenance, event ordering, adapter ownership, trace persistence, audit artifact shape, and boot-owned evidence wiring. |
| Scheduler facade flow | facade behavior is `stable_contract_candidate`; internals are `internal_only` / `legacy_compat` | Preserve `ZeroSystem` and scheduler public lifecycle behavior. Do not expand `scheduler.py` as public API. Actual enqueue primitive remains scheduler-owned. |
| Agent runtime request flow | request semantics are `stable_contract_candidate` | Agent loop may request runtime work but must not own mutation, rollback, repair, recovery, patch, or scheduler private authority. Self-edit must use governed runtime paths. |

## Protected Tests

The following tests must pass before runtime kernel changes are considered safe:

1. `tests/test_runtime_boundary_imports.py`
2. `tests/test_runtime_mutation_authority_boundaries.py`
3. `tests/test_repair_chain_runtime.py`
4. `tests/test_scheduler_parser_helpers.py`

Minimum command pack:

```text
python -m pytest tests/test_runtime_boundary_imports.py -q
python -m pytest tests/test_runtime_mutation_authority_boundaries.py -q
python -m pytest tests/test_repair_chain_runtime.py -q
python -m pytest tests/test_scheduler_parser_helpers.py -q
```

If `python` is not on PATH, use the workspace's known passing bundled Python executable. Existing `datetime.utcnow()` warnings in `core/runtime/mutation_boundary.py` are not part of this freeze gate and must not be cleaned incidentally.

## Mutation-Sensitive Modules

These modules should not be changed casually. They either own runtime authority or sit on a boundary where accidental exposure can weaken the kernel contract.

### Scheduler and Queue Ownership

- `core/tasks/scheduler.py`
- `core/tasks/scheduler_core/*`
- `core/tasks/scheduler_core/task_scheduler_queue.py`
- `core/tasks/scheduler_core/task_dispatcher.py`
- `core/tasks/scheduler_core/worker_pool.py`
- `core/tasks/task_repository.py`
- `core/tasks/task_storage.py`
- `core/tasks/task_workspace.py`
- `core/tasks/task_paths.py`

### Repair and Replay Ownership

- `core/tasks/scheduler_core/repair_injection_execution.py`
- `core/tasks/scheduler_core/repair_replay_continuation.py`
- `core/tasks/scheduler_core/retrying_repair_replay_state.py`
- `core/tasks/runtime_repair_transaction.py`
- `core/tasks/runtime_repair_transaction_review.py`
- `core/tasks/runtime_repair_apply_transaction.py`
- `core/tasks/runtime_repair_controlled_apply.py`
- `core/tasks/runtime_repair_mutation_authorization.py`
- `core/tasks/runtime_repair_mutation_scope_gate.py`
- `core/runtime/governed_repair_api.py`
- `core/runtime/repair_step_injector.py`
- `core/runtime/repair_transaction_execution_bridge.py`
- `core/runtime/repair_rollback.py`

### Mutation and Rollback Ownership

- `core/runtime/mutation_gateway.py`
- `core/runtime/mutation_runtime_pipeline.py`
- `core/runtime/mutation_boundary.py`
- `core/runtime/mutation_patch_apply.py`
- `core/runtime/mutation_sandbox.py`
- `core/runtime/mutation_approval.py`
- `core/runtime/mutation_verification.py`
- `core/runtime/mutation_replay.py`
- `core/runtime/code_chain_patch_restore.py`
- `core/runtime/runtime_execution_transaction.py`
- `core/runtime/runtime_transaction_orchestrator.py`

### Recovery Ownership

- `core/runtime/runtime_recovery_coordinator.py`
- `core/runtime/runtime_recovery_policy.py`
- `core/runtime/runtime_recovery_commit_gate.py`
- `core/runtime/runtime_recovery_approval.py`
- `core/runtime/runtime_recovery_dry_run.py`
- `core/runtime/runtime_recovery_execution.py`
- `core/runtime/runtime_recovery_evidence.py`
- any `core/runtime/runtime_recovery*` module

### Evidence and Trace Ownership

- `core/runtime/runtime_mainline_evidence_seal.py`
- `core/runtime/scheduler_evidence_adapter.py`
- `core/runtime/task_runtime_evidence_adapter.py`
- `core/runtime/step_executor_evidence_adapter.py`
- `core/runtime/runtime_evidence_persistence.py`
- `core/runtime/runtime_evidence_registry.py`
- `core/runtime/runtime_evidence_integration.py`
- `core/runtime/trace_runtime.py`
- `core/runtime/event_sink.py`
- `core/runtime/event_replay.py`
- `core/runtime/event_stream.py`

### Agent and Public Request Boundary

- `core/agent/agent_loop.py`
- `core/agent/agent_component_invoker.py`
- `core/agent/capability_invoker.py`
- `core/agent/repo_edit_review_adapter.py`
- `core/planning/planner.py`
- `core/planning/task_replanner.py`
- `services/system_boot.py`

## Change Rules

### Allowed Without Full Smoke Pack

These changes are allowed with normal focused tests, as long as they do not touch mutation-sensitive modules:

- documentation-only updates;
- comments that do not alter executable statements;
- tests that only add coverage and do not weaken boundary assertions;
- read-only display or formatting changes outside runtime authority paths;
- typo fixes in non-runtime docs.

### Require Protected Smoke Pack

Run the protected tests whenever a change touches:

- any mutation-sensitive module listed above;
- runtime boundary import rules;
- mutation authority radar rules;
- repair transaction, injection, replay, or review code;
- rollback or patch restore code;
- governed mutation gateway or pipeline code;
- recovery policy, coordinator, commit gate, approval, execution, dry-run, or evidence code;
- scheduler public lifecycle, queue, tick, dispatch, finalize, worker release, or compatibility binding code;
- evidence adapters, trace runtime, event sinks, replay, or audit builders;
- agent loop runtime request routing or self-edit flow.

### Require Rollback Plan

A rollback plan is required before changing:

- `scheduler.py` executable logic;
- actual enqueue primitive execution;
- runtime state persistence writes;
- mutation patch application;
- repair transaction commit/apply/injection;
- recovery execution or commit gate behavior;
- evidence persistence or emitted record shape;
- self-edit mutation routing;
- compatibility monkey-patch bindings.

The rollback plan must identify the files touched, the previous behavior being preserved, the tests that prove preservation, and the exact revert path if the change breaks mainline runtime behavior.

### Must Be Blocked Until Reviewed

Block changes until explicit review when they:

- expose `scheduler.py` or `scheduler_core` as a new public API;
- add external imports of scheduler internals, mutation internals, repair transaction internals, recovery internals, queue primitives, or evidence emitters;
- let agent, planner, services, plugins, capability packs, UI, or remote orchestration call direct mutation/rollback/recovery/patch authority;
- bypass policy, guard, approval, rollback, verification, or evidence for mutating operations;
- alter compatibility monkey-patch binding order;
- make recovery execution public before a governed wrapper and dedicated recovery smoke pack exist;
- weaken or remove the boundary import or mutation authority tests;
- clean unrelated warnings or perform broad refactors in the same change.

## Scheduler Freeze Rules

`scheduler.py` must not be expanded as the public runtime API.

Rules:

- scheduler internals must not be imported by external layers;
- `core.tasks.scheduler_core.*` remains internal;
- actual enqueue primitive execution remains scheduler-owned;
- external callers must use governed runtime surface wrappers once they exist;
- until those wrappers exist, `services/system_boot.py` remains the only explicit bootstrap exception for importing `Scheduler`;
- new external access must not call scheduler private methods;
- replay, retry, repair, queue hygiene, pending repair lifecycle, dispatch/finalize routing, and worker release routing must remain scheduler-owned or moved only through targeted extraction with regression coverage.

## Self-Edit Freeze Rules

Self-edit may request runtime mutation only through governed authority paths.

Rules:

- direct internal mutation is forbidden from agent, planner, services, plugin, capability pack, UI, and remote orchestration layers;
- self-edit must not call `StepExecutor`, step handlers, mutation pipeline internals, patch apply primitives, repair transaction lifecycle internals, scheduler private methods, or evidence emitters directly;
- rollback is mandatory for repository-changing self-edit operations;
- verification is mandatory before success is recorded;
- audit/evidence is mandatory for proposal, policy, approval when required, mutation, rollback, verification, and final status;
- agent loop remains request-only and must delegate mutation/rollback execution to runtime/tasks ownership;
- Code Chain patch restore must continue through `core.runtime.code_chain_patch_restore.request_code_chain_patch_restore` unless replaced by a governed runtime wrapper with equivalent behavior.

## Runtime Freeze Candidate Criteria

Declare a Runtime Kernel Freeze Candidate only when all of the following are true:

- protected tests pass without new failures;
- existing warnings are understood and not mixed with unrelated cleanup;
- public, internal mutation, and compatibility legacy surfaces are documented;
- external-facing layers cannot import scheduler/runtime mutation internals directly;
- external-facing layers cannot call obvious mutation/rollback/recovery/patch authority directly;
- repair, rollback, governed mutation, recovery, replay, evidence, scheduler facade, and agent request flows have explicit owners;
- scheduler remains isolated from public API expansion;
- mutation-sensitive changes have rollback plans;
- self-edit uses governed authority paths only;
- recovery remains internal or has a dedicated governed wrapper and regression pack;
- evidence write ownership is preserved;
- compatibility bindings are unchanged or covered by targeted regression tests;
- no file moves or broad refactors are included in the freeze candidate change set.

## Non-Goals

This document does not:

- implement a runtime API;
- implement wrappers;
- change runtime behavior;
- refactor `scheduler.py`;
- move files;
- clean `datetime.utcnow()` warnings;
- alter protected tests;
- approve direct external access to runtime internals;
- declare the Runtime Kernel frozen.
