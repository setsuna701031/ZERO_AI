# Runtime Public Surface Proposal - Phase 4-C.1

Date: 2026-05-18

Source audit: `docs/kernel_surface_audit.md`

This document proposes the public access boundary for the ZERO Runtime Kernel. It is a design proposal only.

## Non-Goals

- No implementation.
- No file moves.
- No scheduler refactor.
- No runtime behavior change.
- No new runtime API module yet.
- No direct exposure of internal mutation, queue, repair, scheduler_core, or compatibility monkey-patch surfaces.

## Boundary Summary

The proposed public runtime surface should be a small facade over the existing runtime kernel. External callers should enter through stable wrappers that preserve policy, guard, approval, rollback, verification, evidence, and scheduler ownership semantics.

`scheduler.py` must not become the public API surface. It remains a runtime owner for queue/tick/dispatch/evidence boundaries, not a general integration API for plugins, UI, remote orchestration, or future agents.

## 1. Candidate Public Runtime APIs

Candidate APIs are based on audit entries marked `keep_public` or `needs_wrapper`.

| Existing module path | Existing symbol | Current purpose | Proposed public name | Stability level |
| --- | --- | --- | --- | --- |
| `services/system_boot.py` | `boot_system` | Construct a complete local ZERO runtime system. | `zero.runtime.boot(workspace_dir)` | stable |
| `services/system_boot.py` | `ZeroSystem.health` | Runtime system health and component status. | `runtime.health()` | stable |
| `services/system_boot.py` | `ZeroSystem.tick` | Advance scheduler/runtime one tick through owned scheduler boundary. | `runtime.tick()` | stable |
| `services/system_boot.py` | `ZeroSystem.run_until_idle` | Run local runtime until idle or max ticks. | `runtime.run_until_idle(max_ticks)` | stable |
| `services/system_boot.py` | queue/status accessors | Read queue rows/snapshots through scheduler facade. | `runtime.queue.snapshot()` / `runtime.queue.rows()` | stable |
| `core/tasks/scheduler.py` | `Scheduler.create_task` | Public task creation through scheduler lifecycle ownership. | `runtime.tasks.create(...)` | stable via wrapper |
| `core/tasks/scheduler.py` | `Scheduler.submit_task` | Create and submit task through scheduler lifecycle. | `runtime.tasks.submit(...)` | stable via wrapper |
| `core/tasks/scheduler.py` | `Scheduler.submit_existing_task` | Submit existing persisted task. | `runtime.tasks.submit_existing(task_id)` | stable via wrapper |
| `core/tasks/scheduler.py` | `Scheduler.pause_task`, `resume_task`, `cancel_task` | Public task lifecycle controls. | `runtime.tasks.pause/resume/cancel(task_id)` | stable via wrapper |
| `core/agent/agent_loop.py` | `AgentLoop.run` | User-facing agent route/task/tool loop. | `runtime.agent.run(input)` | stable |
| `core/planning/planner.py` | `Planner.plan` | Deterministic planning API. | `runtime.planner.plan(request)` | stable via wrapper |
| `core/planning/planner_runtime_entry.py` | `run_planner_runtime_entry` | Contract-normalized planner invocation. | `runtime.planning.run(request)` | stable |
| `core/tasks/planner_gateway_runtime.py` | `run_scheduler_planner_gateway` | Scheduler-safe planner gateway with fallback. | `runtime.planning.for_scheduler(request)` | stable |
| `core/tasks/execution_runtime_entry.py` | `run_execution_runtime_entry` | Contract-normalized execution wrapper around governed executor. | `runtime.execution.run_step(request)` | experimental guarded |
| `core/tasks/scheduler_execution_gateway.py` | `run_scheduler_step_execution_gateway` | Scheduler-context step execution gateway. | `runtime.execution.run_scheduler_step(request)` | experimental guarded |
| `core/runtime/mutation_gateway.py` | `run_governed_mutation` | Public governed mutation gateway. | `runtime.mutations.run_governed(request)` | stable guarded |
| `core/runtime/governed_repair_api.py` | `execute_governed_repair_mutation` | Governed repair mutation API. | `runtime.repairs.execute_governed(request)` | stable guarded |
| `core/tasks/runtime_repair_transaction_review.py` | review build/approve/reject functions | Review contract and approval/rejection flow. | `runtime.repairs.review.build/approve/reject(...)` | stable guarded |
| `core/runtime/runtime_capability_dispatcher.py` | `RuntimeCapabilityDispatcher.dispatch` | Capability dispatch through resolver and intent gate. | `runtime.capabilities.dispatch(operation, ...)` | experimental |
| `core/runtime/runtime_capability_resolver.py` | `RuntimeCapabilityResolver.resolve` | Resolve operation metadata and governance target. | `runtime.capabilities.resolve(operation)` | experimental |
| `core/runtime/runtime_operation_registry.py` | `RuntimeOperationRegistry` | Register/list governed runtime operations. | `runtime.operations.registry` | experimental governed |
| `core/runtime/runtime_boundary.py` | `RuntimeBoundary` | Ownership/mutation boundary requests. | `runtime.boundary.request(...)` | experimental internal-facing |
| `core/runtime/runtime_transition_policy.py` | `RuntimeTransitionPolicy.check_transition` | Runtime transition legality validation. | `runtime.policy.check_transition(...)` | stable |
| `core/runtime/runtime_orchestrator.py` | `RuntimeOrchestrator.evaluate_runtime` | Runtime health, monitor, recovery decision, snapshot aggregation. | `runtime.orchestrator.evaluate()` | experimental |
| `core/runtime/runtime_mainline_evidence_seal.py` | `build_runtime_mainline_evidence_seal` | Build evidence boundaries/adapters/seal. | `runtime.evidence.build_seal(...)` | stable internal setup |
| `core/runtime/trace_runtime.py` | `TraceRuntime` / `build_trace_runtime` | Trace load/save/status runtime. | `runtime.traces` | stable |
| `core/runtime/event_sink.py` | `RuntimeEventSink` | Runtime event persistence sink. | `runtime.events.sink` | stable guarded |
| `core/runtime/event_replay.py` | `RuntimeEventReplay` | Read-only event replay and filtering. | `runtime.events.replay(...)` | stable read-only |
| `core/runtime/event_stream.py` | event stream helpers | Event stream channel/envelope helpers. | `runtime.events.streams` | stable |
| `core/tasks/runtime_kernel_status.py` | status builders/formatters | Read-only runtime kernel status. | `runtime.status.get(...)` | stable read-only |
| `core/tasks/runtime_kernel_timeline.py` | timeline builders/summarizers | Read-only runtime timeline. | `runtime.timeline.get(...)` | stable read-only |
| `core/tasks/runtime_kernel_events.py` | kernel event builders | Read-only runtime event formatting. | `runtime.events.kernel(...)` | stable read-only |
| `core/tasks/runtime_replay_snapshot.py` | `build_runtime_replay_snapshot` | Read-only runtime replay snapshot. | `runtime.replay.snapshot(task)` | stable read-only |
| `core/tasks/runtime_replay_narrative.py` | `build_runtime_replay_narrative` | Read-only replay narrative. | `runtime.replay.narrative(snapshot)` | stable read-only |
| `core/tasks/runtime_audit_artifact.py` | `build_runtime_audit_artifact` | Runtime audit artifact builder. | `runtime.audit.artifact(snapshot)` | stable read-only |
| `core/tasks/runtime_repair_contract.py` | `build_runtime_repair_contract` | Read-only repair contract builder. | `runtime.repairs.contract(...)` | stable read-only |
| `core/tasks/runtime_repair_envelope.py` | `build_runtime_repair_envelope` | Read-only repair envelope builder. | `runtime.repairs.envelope(...)` | stable read-only |
| `core/tasks/runtime_repair_planner_bridge.py` | `build_runtime_repair_planner_bridge` | Repair planner bridge payload. | `runtime.repairs.plan_bridge(...)` | experimental proposal-only |
| `core/tasks/runtime_repair_planner_proposal.py` | `build_runtime_repair_planner_proposal` | Repair planner proposal payload. | `runtime.repairs.propose(...)` | experimental proposal-only |
| `core/tasks/runtime_repair_confirmation.py` | `build_runtime_repair_confirmation_gate` | Repair confirmation gate. | `runtime.repairs.confirmation_gate(...)` | stable guarded |
| `core/tasks/runtime_repair_suggestion.py` | `build_runtime_repair_suggestion` | Repair suggestion/reporting payload. | `runtime.repairs.suggest(...)` | stable read-only |
| `core/tasks/task_repository.py` | `TaskRepository` | Task index persistence. | `runtime.storage.tasks` | internal by default, public only via wrapper |
| `core/tasks/task_paths.py` | `TaskPathManager` | Workspace/task/shared path resolution. | `runtime.paths` | stable guarded |
| `core/tasks/task_workspace.py` | `TaskWorkspace` | Task artifact workspace helper. | `runtime.workspace.tasks` | stable guarded |
| `core/planning/replan_suggestion.py` | suggestion builders | Read-only replan suggestion formatting. | `runtime.planning.replan_suggestions(...)` | stable read-only |
| `core/agent/agent_route_policy.py` | route policy helpers | Route/capability classification helpers. | `runtime.agent.route_policy` | stable read-only |
| `core/agent/model_use_policy.py` | model use policy helpers | Classify model/tool usage. | `runtime.agent.model_policy` | stable read-only |

## Stability Levels

- `stable`: Intended to remain source-compatible after wrapper introduction.
- `stable read-only`: Safe to expose for reporting, status, audit, replay, or planning display; must not mutate runtime.
- `stable guarded`: Public only when policy/approval/verification/rollback/evidence gates are enforced.
- `experimental`: Useful kernel capability, but wrapper shape and governance may change.
- `experimental guarded`: High-risk operation that can become public only behind explicit guardrails.
- `proposal-only`: Produces proposals/contracts, never authorization or execution by itself.
- `internal by default`: Existing symbol may remain importable, but should not be plugin/UI/remote public API without wrapper.

## 2. Required Wrappers

These wrappers are names only. Do not implement them in this phase.

| Internal or legacy surface | Why direct exposure is unsafe | Proposed wrapper name |
| --- | --- | --- |
| `core.tasks.scheduler.Scheduler` private methods and scheduler_core helpers | Direct queue/dispatch/retry/repair calls bypass scheduler ownership and evidence timing. | `RuntimeTaskService` |
| `Scheduler._enqueue_repo_task_if_ready` | Actual queue primitive must stay scheduler-owned. | `RuntimeQueueService.enqueue_if_ready` |
| `core.tasks.scheduler_core.*` | Helpers assume scheduler context and are not API-stable. | `RuntimeSchedulerFacade` |
| `core.runtime.TaskRuntime` mutation methods | Direct runtime-state writes can corrupt lifecycle state. | `RuntimeStateService` |
| `core.runtime.TaskRunner` tick methods | Direct ticks can execute work outside scheduler queue ownership. | `RuntimeExecutionService.run_task_tick` |
| `core.runtime.StepExecutor.execute_step` | Direct step execution can write files, run commands, apply patches. | `GuardedStepExecutionService.execute_step` |
| `core.runtime.step_handlers.*` | Handler calls bypass executor normalization and evidence hooks. | `GuardedStepExecutionService` |
| `core.tasks.execution_guard.ExecutionGuard` | Guard result is not complete authorization. | `RuntimePolicyService.check_step` |
| `core.runtime.repair_step_injector.RepairStepInjector` | Direct repair injection can duplicate steps or violate replay/audit mode. | `RuntimeRepairService.inject_repair_steps` |
| `core.runtime.repair_planner.RepairPlanner` | Repair plans are proposals, not authorization. | `RuntimeRepairPlanningService.propose` |
| `core.tasks.runtime_repair_transaction.*` | Direct lifecycle operations can stage/commit without confirmation context. | `RuntimeRepairTransactionService` |
| `core.runtime.repair_transaction_execution_bridge.execute_committed_runtime_repair_transaction` | Direct execution bypasses governed repair API. | `RuntimeRepairExecutionService.execute_committed` |
| `core.runtime.mutation_runtime_pipeline.run_mutation_runtime_pipeline` | Bypasses gateway validation and session construction. | `RuntimeMutationService.run_governed` |
| `core.runtime.mutation_patch_apply.*` | Direct file mutation. | `RuntimePatchService.apply_verified` |
| `core.runtime.mutation_sandbox.*` | Sandbox operations must be coupled to rollback/evidence. | `RuntimeMutationSandboxService` |
| `core.runtime.mutation_approval.*` | Approval must be tied to operator/auth context. | `RuntimeApprovalService` |
| `core.runtime.runtime_execution_transaction.*` | Direct transaction commit/rollback is unsafe. | `RuntimeTransactionService` |
| `core.runtime.runtime_transaction_orchestrator.RuntimeTransactionOrchestrator` | Needs operation registry, gate checks, audit context. | `RuntimeTransactionWorkflowService` |
| `core.runtime.runtime_recovery*` | Recovery can mutate state/files and must be governed. | `RuntimeRecoveryService` |
| `core.runtime.runtime_state_registry.RuntimeStateRegistry` | Direct registry writes can conflict with TaskRuntime ownership. | `RuntimeStateRegistryService` |
| Evidence adapters and emitters | Direct evidence emission can falsify audit trails. | `RuntimeEvidenceService` |
| `core.agent.capability_invoker.execute_resolved_capability` | Capability execution must pass routing/gate policy. | `RuntimeCapabilityService.execute` |
| `core.agent.agent_component_invoker.*` | Direct component invocation bypasses AgentLoop normalization. | `AgentComponentService` |
| `core.agent.repo_edit_review_adapter.run_agent_repo_edit_review` | Repo edits require repair/mutation governance. | `RuntimeRepoEditReviewService` |
| `core.runtime.task_scheduler.TaskScheduler` | Legacy scheduler base lacks current ownership/evidence semantics. | `RuntimeTaskService` |
| Versioned `_zero_*` monkey-patch symbols | Compatibility implementation details; binding order is behavior-critical. | No public wrapper; keep hidden |

## 3. Mutation-Protected Operations

These operations must always go through policy, guard, approval, rollback, verification, and evidence where applicable.

| Operation | Required controls | Required public route | Never directly import/call |
| --- | --- | --- | --- |
| Queue transition / enqueue / dequeue / cancel | Scheduler ownership, dependency check, worker release, evidence timing. | `runtime.tasks.*` or `runtime.queue.*` wrapper. | `Scheduler._enqueue_repo_task_if_ready`, `TaskSchedulerQueue`, `TaskDispatcher`, `WorkerPool`, scheduler_core queue helpers. |
| Task runtime state write | Transition policy, TaskRuntime normalization, state guard, persistence hygiene. | `runtime.tasks.*`, `runtime.state.*` wrapper. | `TaskRuntime.save_runtime_state`, runtime state registry internals, direct `runtime_state.json` writes. |
| Task tick / execution progression | Scheduler queue ownership, TaskRunner lifecycle, TaskRuntime transitions, StepExecutor guard. | `runtime.tick()`, `runtime.run_until_idle()`, guarded execution wrapper. | `TaskRunner.run_task_tick`, `TaskRunner.run_one_step`, scheduler private dispatch methods. |
| Step execution | ExecutionGuard, path policy, command policy, evidence, result normalization. | `runtime.execution.run_step(...)`. | `StepExecutor.execute_step`, `step_handlers.*`. |
| Command/run_python execution | Command policy, workspace cwd policy, approval if needed, evidence, timeout/result normalization. | `runtime.execution.run_step(...)` with guarded command step. | `CommandStepHandler`, `RunPythonStepHandler`, raw subprocess helpers. |
| File write/append/ensure | Path policy, workspace scope, rollback/backup for repair paths, evidence. | Guarded step or governed mutation wrapper. | `WriteFileStepHandler`, `AppendFileStepHandler`, direct task path writes. |
| Patch/apply_unified_diff | Approval, sandbox, verification, rollback, evidence. | `runtime.mutations.run_governed(...)`. | `mutation_patch_apply`, StepExecutor apply handlers, controlled mutation internals. |
| Governed repair mutation | Scope gate, transaction, review/confirmation, approval, sandbox, verification, rollback. | `runtime.repairs.execute_governed(...)`. | repair transaction execution bridge, repair apply modules, repair injector direct state mutation. |
| Repair step injection | Runtime mode guard, replay/idempotency checks, scheduler continuation ownership. | `runtime.repairs.*` wrapper only after implementation. | `RepairStepInjector.inject_steps_into_state`, `repair_injection_execution`, scheduler v734 internals. |
| Repair transaction approval/rejection | Operator identity, reason, transaction state, confirmation gate. | `runtime.repairs.review.approve/reject(...)`. | confirmation action internals, transaction lifecycle helpers. |
| Runtime recovery | Recovery policy, dry-run, approval, evidence, rollback. | future `runtime.recovery.*` wrapper. | `runtime_recovery*` internals. |
| Runtime transaction commit/rollback | Operation registry, gate integration, state validation, evidence. | future `runtime.transactions.*` wrapper. | execution transaction manager, transaction orchestrator direct methods. |
| Evidence emission | Boundary ownership and monotonic provenance. | `runtime.evidence.*` wrapper or boot-created adapters only. | evidence adapters/emitters direct from plugins/UI. |
| Capability execution | Capability resolver, operation registry, intent gate, policy. | `runtime.capabilities.dispatch(...)`. | `execute_resolved_capability`, agent component invokers. |
| Replay/session verification | Readonly mode, no execution transition, deterministic replay validation. | `runtime.replay.*` wrapper. | replay engine direct mutation paths, retry repair bridge internals. |

Surfaces that must never be directly imported by plugins, capability packs, UI, remote orchestration, or future agents:

- `core.tasks.scheduler_core.*`
- `core.runtime.step_handlers`
- `core.runtime.mutation_runtime_pipeline`
- `core.runtime.mutation_patch_apply`
- `core.runtime.mutation_sandbox`
- `core.runtime.repair_transaction_execution_bridge`
- `core.runtime.repair_step_injector`
- `core.tasks.runtime_repair_transaction`
- `core.tasks.runtime_repair_apply_transaction`
- `core.tasks.runtime_repair_controlled_apply`
- `core.runtime.runtime_execution_transaction`
- `core.runtime.runtime_transaction_orchestrator`
- `core.runtime.runtime_recovery*`
- versioned `_zero_*` symbols in scheduler, planner, task runtime, task runner, and step executor.

## 4. Future Plugin / Runtime Boundaries

### Plugins May Call

Plugins may call only stable or guarded public wrappers:

- `runtime.health()`
- `runtime.status.get(...)`
- `runtime.timeline.get(...)`
- `runtime.events.replay(...)`
- `runtime.audit.artifact(...)`
- `runtime.replay.snapshot(...)`
- `runtime.tasks.create(...)`
- `runtime.tasks.submit(...)`
- `runtime.tasks.cancel(...)`
- `runtime.planning.run(...)`
- `runtime.planning.replan_suggestions(...)`
- `runtime.agent.run(...)`
- `runtime.capabilities.resolve(...)`
- `runtime.capabilities.dispatch(...)`
- `runtime.mutations.run_governed(...)`
- `runtime.repairs.propose(...)`
- `runtime.repairs.review.*`
- `runtime.repairs.execute_governed(...)`

Plugins may receive read-only payloads from:

- runtime status builders;
- runtime timeline builders;
- event replay;
- audit artifact builders;
- repair contract/envelope/suggestion builders;
- planner contract adapters.

### Plugins Must Not Call

Plugins must not call:

- scheduler private methods;
- scheduler_core modules;
- StepExecutor or step handlers directly;
- TaskRunner tick methods directly;
- TaskRuntime write/transition methods directly;
- mutation pipeline internals;
- patch apply internals;
- repair transaction lifecycle internals;
- repair injection internals;
- queue/dispatcher/worker pool internals;
- evidence adapters/emitters directly;
- `_zero_*` compatibility functions;
- direct filesystem writes to task runtime artifacts.

### Plugin Capability Rule

Plugins should describe intent and desired operation. The runtime public surface should resolve, gate, schedule, execute, verify, and record evidence. Plugins should not decide lifecycle state, mutate runtime files, or commit transactions.

## 5. API Ownership Rules

### Public Runtime Access Owner

Public runtime access should be owned by a future facade layer, conceptually:

- `zero.runtime` or `core.runtime.kernel_api`
- backed by `ZeroSystem`, scheduler public lifecycle methods, governed mutation APIs, planner/execution gateway wrappers, evidence/status/read-only builders.

Responsibilities:

- provide stable names;
- hide private scheduler/runtime internals;
- enforce policy and approval boundaries;
- normalize payloads;
- preserve evidence timing;
- support local now and future HTTP/RPC/CLI/UI mappings.

### Internal Mutation Owner

Internal mutation remains owned by the runtime kernel layers:

- Scheduler owns queue/tick/dispatch/evidence timing.
- TaskRuntime owns runtime-state transitions and persistence.
- TaskRunner owns per-task execution progression.
- StepExecutor owns normalized step execution under guard context.
- MutationGateway and GovernedRepair API own governed mutation entry.
- Mutation pipeline owns sandbox/approval/verification/rollback execution.

No plugin/UI/remote caller should own internal mutation.

### Compatibility Legacy Owner

Compatibility legacy access remains owned by existing modules until replaced:

- scheduler versioned compatibility bindings stay in `scheduler.py`;
- planner/task runtime/task runner/step executor `_zero_*` patch symbols remain private implementation details;
- legacy controlled mutation modules remain internal or deprecated behind wrappers;
- `core.runtime.task_scheduler.TaskScheduler` remains legacy compatibility only.

Compatibility surfaces should not be exported by any future public facade.

## 6. Scheduler Isolation Rules

`scheduler.py` must not become the public runtime API surface.

Scheduler should remain:

- task lifecycle owner;
- scheduler loop/tick owner;
- actual enqueue primitive owner;
- dispatch/finalize/worker routing owner;
- runtime evidence timing owner;
- compatibility binding owner.

External layers should not import scheduler private methods or scheduler_core helpers. External layers should use proposed public wrappers such as:

- `runtime.tasks.create(...)`
- `runtime.tasks.submit(...)`
- `runtime.tick()`
- `runtime.queue.snapshot()`
- `runtime.repairs.review.*`
- `runtime.mutations.run_governed(...)`
- `runtime.capabilities.dispatch(...)`

Future wrappers may internally call scheduler public methods, but wrapper consumers should not need to import or instantiate `Scheduler` directly.

## 7. Future Remote / Runtime API Mapping

Design notes only. No endpoints are implemented in this phase.

| Proposed local API | Possible HTTP endpoint | Possible RPC method | Possible CLI command | Possible UI surface |
| --- | --- | --- | --- | --- |
| `runtime.health()` | `GET /runtime/health` | `Runtime.Health` | `zero runtime health` | Runtime health panel |
| `runtime.status.get(...)` | `GET /runtime/status` | `Runtime.Status` | `zero runtime status` | Kernel status view |
| `runtime.timeline.get(...)` | `GET /runtime/timeline` | `Runtime.Timeline` | `zero runtime timeline` | Timeline tab |
| `runtime.events.replay(...)` | `GET /runtime/events/replay` | `Runtime.EventsReplay` | `zero runtime events replay` | Event replay inspector |
| `runtime.audit.artifact(...)` | `GET /runtime/audit/artifact` | `Runtime.AuditArtifact` | `zero runtime audit artifact` | Audit artifact drawer |
| `runtime.tasks.create(...)` | `POST /runtime/tasks` | `Runtime.TasksCreate` | `zero task create` | Task composer |
| `runtime.tasks.submit(...)` | `POST /runtime/tasks/submit` | `Runtime.TasksSubmit` | `zero task submit` | Task run button |
| `runtime.tasks.submit_existing(task_id)` | `POST /runtime/tasks/{id}/submit` | `Runtime.TasksSubmitExisting` | `zero task submit-existing` | Task detail action |
| `runtime.tasks.cancel(task_id)` | `POST /runtime/tasks/{id}/cancel` | `Runtime.TasksCancel` | `zero task cancel` | Task detail action |
| `runtime.tasks.pause/resume(task_id)` | `POST /runtime/tasks/{id}/pause`, `POST /runtime/tasks/{id}/resume` | `Runtime.TasksPause`, `Runtime.TasksResume` | `zero task pause/resume` | Task detail actions |
| `runtime.queue.snapshot()` | `GET /runtime/queue/snapshot` | `Runtime.QueueSnapshot` | `zero queue snapshot` | Queue dashboard |
| `runtime.queue.rows()` | `GET /runtime/queue/rows` | `Runtime.QueueRows` | `zero queue rows` | Queue table |
| `runtime.tick()` | `POST /runtime/tick` | `Runtime.Tick` | `zero runtime tick` | Manual tick control |
| `runtime.run_until_idle(max_ticks)` | `POST /runtime/run-until-idle` | `Runtime.RunUntilIdle` | `zero runtime run-until-idle` | Runtime control panel |
| `runtime.agent.run(input)` | `POST /runtime/agent/run` | `Runtime.AgentRun` | `zero agent run` | Chat/input box |
| `runtime.planning.run(request)` | `POST /runtime/planning/run` | `Runtime.PlanningRun` | `zero planner run` | Plan preview |
| `runtime.planning.replan_suggestions(...)` | `GET /runtime/planning/replan-suggestions` | `Runtime.ReplanSuggestions` | `zero replan suggestions` | Replan suggestions panel |
| `runtime.execution.run_step(request)` | `POST /runtime/execution/step` | `Runtime.ExecutionRunStep` | `zero execution run-step` | Restricted admin/debug only |
| `runtime.capabilities.resolve(operation)` | `GET /runtime/capabilities/{operation}` | `Runtime.CapabilitiesResolve` | `zero capability resolve` | Capability inspector |
| `runtime.capabilities.dispatch(...)` | `POST /runtime/capabilities/dispatch` | `Runtime.CapabilitiesDispatch` | `zero capability dispatch` | Capability runner |
| `runtime.mutations.run_governed(request)` | `POST /runtime/mutations/governed` | `Runtime.MutationsRunGoverned` | `zero mutation run-governed` | Governed mutation workflow |
| `runtime.repairs.propose(...)` | `POST /runtime/repairs/propose` | `Runtime.RepairsPropose` | `zero repair propose` | Repair proposal UI |
| `runtime.repairs.review.build(...)` | `POST /runtime/repairs/review` | `Runtime.RepairsReviewBuild` | `zero repair review` | Review queue item |
| `runtime.repairs.review.approve(...)` | `POST /runtime/repairs/review/{id}/approve` | `Runtime.RepairsReviewApprove` | `zero repair approve` | Approve button |
| `runtime.repairs.review.reject(...)` | `POST /runtime/repairs/review/{id}/reject` | `Runtime.RepairsReviewReject` | `zero repair reject` | Reject button |
| `runtime.repairs.execute_governed(...)` | `POST /runtime/repairs/execute-governed` | `Runtime.RepairsExecuteGoverned` | `zero repair execute-governed` | Governed repair execution panel |
| `runtime.traces` | `GET /runtime/traces`, `POST /runtime/traces` | `Runtime.TracesRead/Write` | `zero trace ...` | Trace viewer |
| `runtime.evidence.build_seal(...)` | internal setup endpoint only | `Runtime.EvidenceBuildSeal` | admin/setup only | Diagnostics/admin only |

Remote API guard notes:

- Mutating endpoints must require identity, workspace scope, approval context, and audit evidence.
- `runtime.execution.run_step` should be restricted to local/admin/debug contexts unless wrapped by a task or mutation workflow.
- Repair and mutation endpoints must preserve approval, rollback, verification, and evidence semantics.
- Queue/tick endpoints must preserve scheduler ownership and must not expose scheduler private methods.

## 8. Non-Goals Repeated

- This proposal does not create `zero.runtime` or `core.runtime.kernel_api`.
- This proposal does not change imports or exports.
- This proposal does not move files.
- This proposal does not refactor `scheduler.py`.
- This proposal does not implement HTTP/RPC/CLI/UI endpoints.
- This proposal does not approve direct external access to internal mutation surfaces.
- This proposal does not change runtime behavior.
