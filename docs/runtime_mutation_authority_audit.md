# Runtime Ownership / Mutation Authority Audit - Phase 4-C.2

Date: 2026-05-18

Source documents:

- `docs/kernel_surface_audit.md`
- `docs/runtime_public_surface_proposal.md`

This document defines which ZERO runtime layers are allowed to read, request, mutate, approve, rollback, replay, repair, recover, patch, or override runtime state. It is a design/audit document only.

## Non-Goals

- No implementation.
- No behavior change.
- No scheduler refactor.
- No file moves.
- No wrapper implementation.
- No new runtime API creation.

## Authority Categories

| Authority | Meaning | Allowed examples | Not allowed |
| --- | --- | --- | --- |
| `read_only` | May inspect runtime state, status, event logs, replay snapshots, audit artifacts, timelines, and public task metadata. | Status views, queue snapshots, replay narratives, audit artifact rendering. | Mutating task status, writing runtime files, enqueueing, applying patches. |
| `request_only` | May submit an intent/request/proposal to an owning runtime layer, but may not execute or mutate directly. | Plugin asks to create task, planner returns plan, agent asks scheduler to submit. | Direct TaskRuntime writes, StepExecutor calls, direct patch apply. |
| `governed_mutation` | May initiate mutation only through policy, guard, approval, rollback, verification, and evidence-controlled gateway. | `run_governed_mutation`, governed repair mutation. | Direct mutation pipeline, patch apply primitive, repair injector. |
| `approval_authority` | May approve/reject a pending governed action in an authenticated review context. | Runtime repair review approve/reject. | Fabricating approval data or committing transactions directly. |
| `rollback_authority` | May execute rollback only through transaction/recovery/mutation pipeline controls. | Rollback through mutation runtime or recovery runtime. | Direct file restore helpers from external layers. |
| `replay_authority` | May reconstruct/read replay state in readonly mode and validate determinism. | Runtime event replay, replay snapshot/narrative. | Replay that triggers execution, retry, queue mutation, or repair injection. |
| `recovery_authority` | May plan/run recovery only through recovery policy, dry-run, approval, audit, and rollback controls. | Future `RuntimeRecoveryService`. | Direct `runtime_recovery*` execution internals. |
| `patch_authority` | May apply patches only under governed mutation or repair execution pipeline. | Governed mutation patch apply after approval and verification plan. | `mutation_patch_apply` direct import/call. |
| `override_authority` | May override normal runtime state only in narrowly scoped system/internal recovery flows with audit evidence. | System-level recovery, explicit admin override in future. | Plugins/UI changing runtime state or queue status directly. |
| `forbidden_direct_access` | Must not import or call the surface directly. | scheduler_core, step handlers, mutation pipeline internals, `_zero_*` compatibility symbols. | Any external direct usage. |

## Layer Authority Matrix

| Layer | Read | Request | Mutate | Approve | Rollback | Replay | Repair | Recover | Patch | Override | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `plugin` | `read_only` | `request_only` | no direct | no direct | no direct | read-only only | request/proposal only | request only | no direct | none | Plugins may call future public wrappers, never internals. |
| `capability_pack` | `read_only` | `request_only` | no direct | no direct | no direct | read-only only | request/proposal only | request only | no direct | none | Capability packs describe operations; dispatcher/gates own execution. |
| `UI` | `read_only` | `request_only` | no direct | through review wrapper | no direct | read-only only | review/proposal only | request only | no direct | none | UI may render and submit user decisions through governed APIs. |
| `remote_orchestration` | `read_only` | `request_only` | no direct | through authenticated review wrapper | no direct | read-only only | governed request only | governed request only | no direct | admin-only future | Remote calls require identity, workspace scope, and audit evidence. |
| `agent_loop` | `read_only` | `request_only` | via scheduler/gateway only | no direct | no direct | read-only only | request/governed repair only | request only | no direct | none | AgentLoop can ask scheduler/runtime facade, not touch internals. |
| `planner` | `read_only` | `request_only` | none | none | none | none | proposal only | none | none | none | Planner produces plans/proposals, never authorization or execution. |
| `scheduler_facade` | read public state | task lifecycle request owner | controlled public lifecycle only | forwards review | no direct except delegated | read-only replay views | request/governed bridge | request only | no direct | none | Future facade over Scheduler public methods, not private internals. |
| `scheduler_internal` | full scheduler-owned read | owns queue/tick requests | queue/status coordination | forwards review bindings | worker/queue cleanup only, not patch rollback | retry/replay coordination only | compatibility repair bridge coordination | no recovery execution | no patch authority | limited compatibility overrides | Internal coordinator, not external mutation authority. |
| `mutation_runtime` | own mutation state | accepts governed requests | `governed_mutation` | consumes approval | `rollback_authority` | mutation replay/audit | repair mutation execution via governed route | no broad recovery | `patch_authority` | no general override | Owns sandbox, approval, verification, apply, rollback, evidence. |
| `repair_runtime` | repair state/contracts | accepts repair proposals/transactions | governed repair only | review/confirmation authority via wrappers | rollback through mutation/recovery pipeline | repair replay readonly | `governed_mutation` repair authority | request recovery if needed | patch only through mutation runtime | no direct override | Owns repair transaction/governance semantics behind public wrappers. |
| `recovery_runtime` | recovery state/audit | accepts recovery request | governed recovery only | may require approval | `rollback_authority` | replay validation | may request repair | `recovery_authority` | patch only through mutation runtime | limited audited override | Recovery must be dry-run/approval/evidence controlled. |
| `policy_guard` | read policy inputs | validates requests | no mutation | no approval | no rollback | no replay | no repair | no recovery | no patch | no override | Policy/guard returns decisions, not execution. |
| `verification_runtime` | read artifacts/results | validates verification requests | no mutation except report artifacts | no approval | no rollback | replay verification allowed | validates repair result | validates recovery result | no patch | no override | Verification can fail/pass, not apply. |
| `system_boot` | bootstrap read | constructs owners | no direct mutation beyond initialization | no approval | no rollback | no replay execution | no repair execution | no recovery execution | no patch | no override | Boot wires components and evidence adapters; runtime owners perform work. |

## Mutation Rules

### Universal Mutation Rule

Any operation that changes runtime state, task state, queue state, files, patches, repair transactions, recovery state, evidence records, or execution lifecycle must go through all applicable controls:

- policy;
- guard;
- approval;
- rollback;
- verification;
- audit/evidence.

Skipping a control is allowed only for explicitly read-only operations or for internal no-op/status formatting operations.

### Operation Control Matrix

| Operation | Policy | Guard | Approval | Rollback | Verification | Audit/evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Task create/submit | yes | dependency/queue policy | usually no | no | no | yes |
| Queue enqueue/dequeue/cancel | yes | scheduler transition guard | no | worker release as needed | no | yes |
| Task tick/dispatch | yes | scheduler dispatch gate | no | no | result validation | yes |
| Step execution | yes | yes | depends on step risk | for mutation steps | yes for mutation/verify steps | yes |
| Command/run_python | yes | yes | for elevated/high-risk commands | no by default | result validation | yes |
| File write/append/ensure | yes | path guard | for external/governed mutation | yes when governed | yes when governed | yes |
| Patch/apply_unified_diff | yes | path/scope guard | yes | yes | yes | yes |
| Governed mutation | yes | scope guard | yes unless explicit dry-run policy | yes | yes | yes |
| Governed repair mutation | yes | repair scope gate | yes | yes | yes | yes |
| Repair step injection | yes | runtime mode/replay guard | no direct external approval; transaction may require approval | rollback via repair/mutation pipeline | yes | yes |
| Runtime-state write | transition policy | state guard | for external override | yes for recovery/override | state validation | yes |
| Recovery execution | recovery policy | runtime gate | yes for mutating recovery | yes | yes | yes |
| Rollback execution | rollback policy | scope guard | may require approval | owned operation | verify restored state | yes |
| Replay | readonly policy | readonly guard | no | no | determinism validation | yes |
| Evidence write | evidence policy | boundary ownership | no | no | schema validation | yes |
| Override | explicit override policy | state guard | yes/admin | yes where possible | yes | mandatory |

## Forbidden Direct Access

External layers must never directly import or call these runtime internals:

- `core.tasks.scheduler_core.*`
- `core.tasks.scheduler.Scheduler` private methods
- `Scheduler._enqueue_repo_task_if_ready`
- `Scheduler._sync_runner_result_and_requeue_if_ready`
- `Scheduler.cleanup_task_queue_hygiene` as an external API
- `Scheduler._persist_task_payload`
- `Scheduler._write_runtime_state_file_safe`
- `core.runtime.step_handlers.*`
- `core.runtime.step_executor.StepExecutor.execute_step`
- `core.runtime.task_runner.TaskRunner.run_task_tick`
- `core.runtime.task_runner.TaskRunner.run_one_step`
- `core.runtime.task_runtime.TaskRuntime.save_runtime_state`
- `TaskRuntime.mark_running`, `advance_step`, `record_step_failure`, `mark_failed`, `mark_finished`
- `core.runtime.repair_step_injector.RepairStepInjector.inject_steps_into_state`
- `core.runtime.repair_transaction_execution_bridge.execute_committed_runtime_repair_transaction`
- `core.tasks.runtime_repair_transaction.*` lifecycle internals
- `core.tasks.runtime_repair_apply_transaction.*`
- `core.tasks.runtime_repair_controlled_apply.*`
- `core.runtime.mutation_runtime_pipeline.run_mutation_runtime_pipeline`
- `core.runtime.mutation_patch_apply.*`
- `core.runtime.mutation_sandbox.*`
- `core.runtime.runtime_execution_transaction.*`
- `core.runtime.runtime_transaction_orchestrator.RuntimeTransactionOrchestrator` direct commit/rollback paths
- `core.runtime.runtime_recovery*` execution internals
- direct evidence adapters/emitters outside boot-created ownership
- direct file writes to task `runtime_state.json`, task snapshots, queue state, trace files, or evidence logs
- versioned `_zero_*` compatibility functions in scheduler, planner, step executor, task runner, and task runtime.

Forbidden direct access applies to:

- plugins;
- capability packs;
- UI;
- remote orchestration;
- future agents;
- tool integrations;
- third-party extensions.

## Scheduler Ownership Rules

`scheduler.py` is not the public runtime owner.

Scheduler internals may coordinate execution, but they must not become external mutation authority.

Scheduler owns:

- scheduler loop and tick timing;
- actual enqueue primitive execution;
- dispatch/finalize/worker routing;
- task lifecycle persistence coordination;
- runtime evidence timing;
- compatibility monkey-patch bindings;
- legacy queue hygiene and pending repair lifecycle until migrated.

Scheduler does not externally expose:

- private queue mutation;
- private replay/retry mutation;
- repair injection internals;
- scheduler_core helpers;
- compatibility `_zero_*` functions;
- direct runtime-state writes.

Future external layers must use governed public surface wrappers, for example:

- `runtime.tasks.create(...)`
- `runtime.tasks.submit(...)`
- `runtime.tick()`
- `runtime.queue.snapshot()`
- `runtime.mutations.run_governed(...)`
- `runtime.repairs.review.*`
- `runtime.repairs.execute_governed(...)`
- `runtime.capabilities.dispatch(...)`

Scheduler may remain an implementation dependency behind those wrappers, but callers should not import scheduler internals.

## Self-Edit Safety Implications

Future self-edit runtime must request mutation authority instead of directly touching internals.

Required self-edit flow:

1. Self-edit agent or planner produces a proposal only.
2. Proposal is classified as governed mutation or governed repair.
3. Runtime public wrapper submits the request to mutation/repair authority.
4. Policy and scope guard validate target files and operation intent.
5. Approval/confirmation is required for high-risk or repository-changing edits.
6. Mutation runtime prepares sandbox and rollback plan.
7. Verification runtime defines required checks.
8. Mutation runtime applies patch/write only after approval and verification plan are present.
9. Runtime evidence records proposal, approval, mutation, verification, rollback refs, and final status.
10. Scheduler is notified through public lifecycle/queue/tick surfaces only when task orchestration is required.

Self-edit must not:

- import `StepExecutor` or step handlers directly;
- call mutation pipeline internals;
- call patch apply primitives;
- write repo files directly;
- write `runtime_state.json` directly;
- call scheduler private enqueue/retry/repair methods;
- call repair transaction lifecycle internals directly;
- forge approval payloads;
- bypass evidence emission.

Self-edit authority category:

- proposal generation: `request_only`;
- mutation execution: `governed_mutation`;
- approval: `approval_authority` only through authenticated review wrapper;
- rollback: `rollback_authority` only through mutation/recovery runtime;
- patch: `patch_authority` only through governed mutation pipeline;
- override: no authority unless future admin override wrapper exists.

## Future Enforcement Candidates

Design notes only. No enforcement is implemented by this audit.

### Import Boundary Tests

Add tests or lint rules that prevent plugin/UI/capability/remote modules from importing:

- `core.tasks.scheduler_core`
- `core.runtime.step_handlers`
- `core.runtime.mutation_runtime_pipeline`
- `core.runtime.mutation_patch_apply`
- `core.runtime.repair_transaction_execution_bridge`
- `core.tasks.runtime_repair_transaction`
- `core.runtime.runtime_execution_transaction`
- versioned `_zero_*` symbols.

### Authority Annotations

Add module-level or symbol-level annotations in a future docs/code-comment pass:

- `@runtime_authority("read_only")`
- `@runtime_authority("request_only")`
- `@runtime_authority("governed_mutation")`
- `@runtime_authority("forbidden_direct_access")`

These annotations should be documentation/metadata first, enforcement later.

### Runtime Permission Checks

Future public wrappers should check:

- caller identity;
- caller layer type;
- workspace scope;
- operation type;
- risk level;
- required approval;
- readonly/replay/audit mode;
- runtime owner.

### Audit Evidence Requirements

Mutating operations should require evidence fields:

- request id;
- caller id/layer;
- task id or runtime object id;
- operation;
- policy decision;
- guard decision;
- approval id when required;
- rollback id when applicable;
- verification id/checks;
- replay/audit refs when applicable;
- final status.

### Policy Gate Requirements

Future policy gates should enforce:

- plugins and capability packs are request-only by default;
- UI and remote orchestration cannot mutate directly;
- planner output is proposal-only;
- agent loop cannot directly execute mutation internals;
- scheduler private methods are not external API;
- mutation and repair execution require governed gateways;
- recovery requires recovery-specific policy and evidence;
- readonly runtime modes cannot transition to execution or mutation statuses.

## Authority Boundary Statement

ZERO runtime mutation authority belongs to the runtime kernel layers that own policy, guard, approval, rollback, verification, and evidence. External layers may read and request. They may not mutate directly.

The public runtime surface should expose stable, governed wrappers. Internal mutation surfaces should remain private. Compatibility legacy surfaces should remain hidden until replaced or deprecated.
