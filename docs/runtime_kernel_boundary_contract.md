# ZERO Runtime Kernel Boundary Contract

Date: 2026-05-18

Source documents:

- `docs/kernel_surface_audit.md`
- `docs/runtime_public_surface_proposal.md`
- `docs/runtime_mutation_authority_audit.md`

This document is the Runtime Kernel Boundary Contract for ZERO. It is the single source of truth for runtime surface classification, public access, mutation authority, scheduler isolation, self-edit safety, and future enforcement direction.

## Contract Scope

The runtime kernel boundary separates stable external access from internal mutation machinery. External callers may read runtime state and submit governed requests. They must not directly mutate scheduler, task runtime, queue, repair, replay, recovery, patch, transaction, or evidence internals.

Normative language:

- `must` means required by this contract.
- `must not` means forbidden by this contract.
- `may` means allowed only within the stated authority.
- `future wrapper` means a proposed public API boundary, not an implementation created by this document.

## Runtime Surface Classification

### PUBLIC_RUNTIME_SURFACE

Public runtime surfaces are stable or intended external-facing APIs. They may be exposed directly only when they preserve policy, guard, scheduler ownership, evidence, and read-only semantics. High-risk surfaces in this class still require governed wrappers.

| Surface | Current modules/symbols | Contract status | External exposure rule |
| --- | --- | --- | --- |
| System boot and local runtime facade | `services/system_boot.py`: `boot_system`, `ZeroSystem` | `keep_public` | Public facade is allowed. Direct mutation through exposed internals such as `.scheduler` or `.task_runtime` must not be treated as public API. |
| Scheduler public lifecycle | `core/tasks/scheduler.py`: `create_task`, `submit_task`, `submit_existing_task`, `pause_task`, `resume_task`, `cancel_task`, `tick`, `run_once`, `run_next`, queue views | `keep_public` behind future facade | Public lifecycle methods are acceptable. Private scheduler methods and `scheduler_core` helpers are forbidden external access. |
| Agent entry | `core/agent/agent_loop.py`: `AgentLoop.run` | `keep_public` | May route work through scheduler and governed runtime services. Must not expose internal mutation authority. |
| Planner and planner gateway | `Planner.plan`, `run_planner_runtime_entry`, `run_scheduler_planner_gateway`, planner contract adapters | `keep_public` | Plan/proposal generation only. Planner output is not authorization to execute or mutate. |
| Guarded execution gateways | `run_execution_runtime_entry`, `run_scheduler_step_execution_gateway` | `needs_wrapper` | Public only through guarded execution wrappers with policy, scheduler context, and evidence. |
| Governed mutation | `run_governed_mutation`, `execute_governed_repair_mutation` | `keep_public` | Public mutation entry must preserve policy, approval, rollback, verification, and evidence. |
| Capability dispatch | `RuntimeCapabilityDispatcher`, `RuntimeCapabilityResolver`, `RuntimeOperationRegistry` | `keep_public` with governance | Public capability route must use resolver, operation registry, intent gates, and risk classification. |
| Runtime boundary and policy | `RuntimeBoundary`, `RuntimeTransitionPolicy`, `RuntimeOrchestrator` | `keep_public` or `needs_wrapper` | May validate or request runtime operations. Policy decisions do not equal direct mutation authority. |
| Evidence, traces, events | trace runtime, event sink/replay/stream helpers, mainline evidence seal builders | `keep_public` with write controls | Read APIs may be public. Evidence writes must be boot-owned or wrapper-governed. |
| Status, timeline, replay, audit builders | runtime kernel status/timeline/events, replay snapshot/narrative, audit artifact/registry | `keep_public` | Read-only public reporting surface. Must not mutate runtime. |
| Repair reporting and review contracts | repair contract/envelope/planner proposal/suggestion/confirmation/review builders | `keep_public` or `needs_wrapper` | Proposal and display surfaces are read-only. Approval/rejection must go through authenticated review wrappers. |
| Task models and workspace helpers | `TaskRepository`, `TaskPathManager`, `TaskWorkspace`, task models/state helpers | `keep_public` with constrained use | Models and path helpers may be public. Repository writes must be owned by scheduler/runtime wrappers. |
| Agent policies | route policy, loop decision, model use policy | `keep_public` or `needs_wrapper` | Policy and decision output may guide requests, not mutate runtime directly. |

### INTERNAL_MUTATION_SURFACE

Internal mutation surfaces are implementation machinery. Plugins, capability packs, UI, remote orchestration, future agents, and third-party extensions must not import or call them directly.

| Surface | Current modules/symbols | Contract status | Risk if exposed |
| --- | --- | --- | --- |
| Runtime state transitions | `TaskRuntime` mutation methods, state registry, state machine | `internal_only` | Can corrupt lifecycle state, bypass transition policy, or reopen terminal tasks. |
| Task execution progression | `TaskRunner.run_task_tick`, `run_one_step` | `internal_only` | Can execute work outside scheduler queue ownership and evidence timing. |
| Step execution internals | `StepExecutor.execute_step`, `core.runtime.step_handlers.*` | `internal_only` | Can run commands, write files, apply patches, or bypass guards. |
| Scheduler internals | `core.tasks.scheduler_core.*`, scheduler private queue/replay/repair/persistence methods | `internal_only` | Assumes scheduler-owned context and can desync queue, retry, repair, or evidence state. |
| Repair injection and replay helpers | `repair_injection_execution.py`, `repair_replay_continuation.py`, `retrying_repair_replay_state.py`, `code_chain_tick_replay_bridge.py` | `internal_only` | Can duplicate repair steps, alter replay continuation, or bypass idempotent scheduler ownership. |
| Repair runtime mutation | repair injector, repair planner internals, rollback helpers, repair transaction lifecycle/apply/control/authorization/scope modules | `internal_only` or `needs_wrapper` | Can stage, approve, inject, commit, apply, or roll back repair without governance. |
| Mutation runtime internals | mutation pipeline, session, sandbox, patch apply, approval, verification, replay | `internal_only` | Can mutate files or audit trails without approval, rollback, verification, or evidence. |
| Runtime transactions and recovery | execution transaction manager, transaction orchestrator, runtime plan executor, `runtime_recovery*` modules | `internal_only` or `needs_wrapper` | Can commit, roll back, recover, or override runtime state outside policy gates. |
| Queue and worker primitives | `TaskQueue`, `TaskSchedulerQueue`, `TaskDispatcher`, `WorkerPool` | `internal_only` | Can bypass dependency checks, worker release routing, and scheduler evidence. |
| Agent execution internals | capability invoker, agent component invoker, repo edit review adapter | `internal_only` or `needs_wrapper` | Can bypass route policy, capability gates, and governed mutation review. |
| Evidence emitters and adapters | scheduler/task runtime/step executor evidence adapters, evidence persistence/registry/integration | `internal_only` with read wrappers | Direct writes can falsify audit sequence or poison evidence. |

### COMPATIBILITY_LEGACY_SURFACE

Compatibility legacy surfaces exist to preserve current flows. They must remain hidden from public runtime APIs until replaced or deprecated.

| Surface | Current modules/symbols | Contract status | External exposure rule |
| --- | --- | --- | --- |
| Scheduler compatibility bindings | versioned `_zero_v7xx/_zero_v3xx` functions and `Scheduler.* = ...` bindings in `scheduler.py` | `legacy_compat` | Must not be called externally. Binding order is behavior-critical. |
| Step executor compatibility bindings | versioned `_zero_v7xx/_zero_v8xx` handlers and registration functions | `legacy_compat` | Must remain behind `StepExecutor` initialization and guarded execution. |
| Task runner/runtime compatibility bindings | versioned `_zero_v7xx/_zero_v8xx/_zero_v9xx` functions | `legacy_compat` | Must not be public mutation API. |
| Planner compatibility bindings | versioned planner route/repair functions | `legacy_compat` | Must remain planner implementation details. |
| Legacy scheduler and simple runner | `core.runtime.task_scheduler.TaskScheduler`, `core/tasks/simple_step_runner.py` | `legacy_compat` | Do not expose instead of current scheduler/runtime facade. |
| Legacy mutation/recovery adapters | `controlled_mutation_*`, repair transaction gateway adapter, recovery trace adapters | `legacy_compat` or `needs_deprecation` | Must not become new public mutation pathways. |
| Legacy repair apply/queue contracts | repair confirmation actions, repair replay queue, repair apply executor contracts | `legacy_compat` | Use governed review/repair wrappers instead. |

## Runtime Public Access Model

The public access model is facade-first. External callers should use future governed public wrappers backed by existing runtime owners. They should not import private modules because a symbol is importable.

### Candidate Public Runtime APIs

| Proposed public API | Backing surface | Purpose | Stability |
| --- | --- | --- | --- |
| `zero.runtime.boot(workspace_dir)` | `boot_system` | Construct a local ZERO runtime system. | stable |
| `runtime.health()` | `ZeroSystem.health` | Read component and runtime health. | stable read-only |
| `runtime.tick()` | `ZeroSystem.tick`, scheduler tick | Advance runtime through scheduler ownership. | stable guarded |
| `runtime.run_until_idle(max_ticks)` | `ZeroSystem.run_until_idle` | Run scheduler-owned ticks until idle. | stable guarded |
| `runtime.tasks.create(...)` | scheduler public lifecycle | Create task through scheduler/task repository ownership. | stable via wrapper |
| `runtime.tasks.submit(...)` | scheduler public lifecycle | Submit task through scheduler queue ownership. | stable via wrapper |
| `runtime.tasks.submit_existing(task_id)` | scheduler public lifecycle | Submit existing persisted task. | stable via wrapper |
| `runtime.tasks.pause/resume/cancel(task_id)` | scheduler public lifecycle | Lifecycle control through scheduler ownership. | stable via wrapper |
| `runtime.queue.snapshot()` / `runtime.queue.rows()` | scheduler queue views | Read queue state. | stable read-only |
| `runtime.agent.run(input)` | `AgentLoop.run` | User-facing agent entry. | stable |
| `runtime.planning.run(request)` | planner runtime entry | Normalize and run planning. | stable |
| `runtime.planning.for_scheduler(request)` | scheduler planner gateway | Scheduler-safe planning bridge. | stable internal-facing |
| `runtime.execution.run_step(request)` | execution runtime entry | Guarded step execution. | experimental guarded |
| `runtime.execution.run_scheduler_step(request)` | scheduler execution gateway | Scheduler-context step execution. | experimental guarded |
| `runtime.capabilities.resolve(operation)` | capability resolver | Resolve operation metadata. | experimental read-only |
| `runtime.capabilities.dispatch(...)` | capability dispatcher | Dispatch governed runtime capability. | experimental guarded |
| `runtime.mutations.run_governed(request)` | mutation gateway | Governed mutation entry. | stable guarded |
| `runtime.repairs.propose(...)` | repair planner/proposal builders | Produce repair proposal only. | experimental proposal-only |
| `runtime.repairs.review.build/approve/reject(...)` | repair transaction review | Review and authenticated approval/rejection. | stable guarded |
| `runtime.repairs.execute_governed(request)` | governed repair API | Execute governed repair mutation. | stable guarded |
| `runtime.status.get(...)` | status builders | Runtime status display. | stable read-only |
| `runtime.timeline.get(...)` | timeline builders | Runtime timeline display. | stable read-only |
| `runtime.events.replay(...)` | event replay | Read event timeline/replay. | stable read-only |
| `runtime.replay.snapshot(...)` | replay snapshot builder | Build read-only replay snapshot. | stable read-only |
| `runtime.audit.artifact(...)` | audit artifact builder | Build audit artifact. | stable read-only |
| `runtime.traces` | trace runtime | Read/write trace data through controlled trace runtime. | stable guarded for writes |
| `runtime.evidence.*` | evidence seal/service wrapper | Evidence setup/read/write under ownership. | internal setup or guarded |

### Wrapper Requirements

The following internal or legacy surfaces require wrappers before any external use:

| Internal surface | Required wrapper name | Required protection |
| --- | --- | --- |
| Scheduler public/private lifecycle split | `RuntimeTaskService` | Hide private methods; preserve scheduler ownership and evidence timing. |
| Actual enqueue primitive | `RuntimeQueueService.enqueue_if_ready` | Keep primitive execution in scheduler; expose only governed request/snapshot APIs. |
| `core.tasks.scheduler_core.*` | `RuntimeSchedulerFacade` | Prevent external dependence on helper implementation details. |
| `TaskRuntime` mutation methods | `RuntimeStateService` | Enforce transition policy, state hygiene, and persistence ownership. |
| `TaskRunner` tick methods | `RuntimeExecutionService.run_task_tick` | Preserve scheduler queue ownership and worker routing. |
| `StepExecutor` and step handlers | `GuardedStepExecutionService` | Enforce execution guard, path policy, evidence, and result normalization. |
| `ExecutionGuard` | `RuntimePolicyService.check_step` | Treat guard output as policy input, not full authorization. |
| Repair planner/injector/transactions | `RuntimeRepairPlanningService`, `RuntimeRepairService`, `RuntimeRepairTransactionService` | Separate proposals, approval, injection, execution, rollback, and evidence. |
| Mutation pipeline/sandbox/patch/approval | `RuntimeMutationService`, `RuntimeMutationSandboxService`, `RuntimePatchService`, `RuntimeApprovalService` | Preserve policy, approval, rollback, verification, evidence, and scope controls. |
| Runtime transaction/recovery internals | `RuntimeTransactionService`, `RuntimeRecoveryService` | Enforce operation registry, gates, approval, dry-run, rollback, and audit evidence. |
| Evidence adapters/emitters | `RuntimeEvidenceService` | Preserve boot-owned provenance and prevent forged records. |
| Capability/component invokers | `RuntimeCapabilityService`, `AgentComponentService` | Route through resolver, intent gate, and agent normalization. |
| `_zero_*` compatibility symbols | no public wrapper | Keep hidden until removed or replaced. |

### External Access Boundaries

Plugins, capability packs, UI, remote orchestration, and future agents may call stable public wrappers for reading, requesting, planning, dispatching, reviewing, and governed mutation. They must not directly import or call scheduler private methods, `scheduler_core`, `TaskRuntime` write methods, `TaskRunner` tick methods, `StepExecutor`, step handlers, mutation pipeline internals, repair transaction/injection internals, recovery execution internals, queue primitives, evidence emitters, or `_zero_*` compatibility symbols.

## Mutation Authority Model

### Authority Categories

| Authority | Meaning |
| --- | --- |
| `read_only` | May inspect runtime status, task metadata, queue snapshots, replay views, timelines, audit artifacts, traces, and evidence views. |
| `request_only` | May submit intent, proposal, plan, task request, capability request, or review request to an owning runtime layer. |
| `governed_mutation` | May initiate mutation only through policy, guard, approval, rollback, verification, and evidence-controlled gateways. |
| `approval_authority` | May approve or reject a governed action only in authenticated review context. |
| `rollback_authority` | May execute rollback only through transaction, mutation, or recovery controls. |
| `replay_authority` | May reconstruct or validate replay state in readonly mode. Must not trigger mutation. |
| `recovery_authority` | May plan or execute recovery only through recovery policy, dry-run, approval, rollback, verification, and evidence. |
| `patch_authority` | May apply patches only inside governed mutation or governed repair execution. |
| `override_authority` | May override normal state only in narrowly scoped internal/admin recovery flows with mandatory evidence. |
| `forbidden_direct_access` | Must not import or call the runtime surface directly. |

### Authority Ownership

Runtime mutation authority belongs to runtime kernel owners, not external callers:

- Scheduler owns loop/tick timing, queue ownership, dispatch/finalize coordination, actual enqueue primitive execution, task lifecycle persistence coordination, and scheduler evidence timing.
- TaskRuntime owns runtime state transitions and persistence normalization.
- TaskRunner owns per-task execution progression under scheduler coordination.
- StepExecutor owns normalized step execution under guard and evidence context.
- Mutation runtime owns sandbox, approval, patch application, verification, rollback, and mutation evidence.
- Repair runtime owns repair proposals, transactions, confirmation/review, injection coordination, governed repair execution, and repair evidence.
- Recovery runtime owns recovery planning, dry-run, approval, rollback, verification, and audited override flows.
- Policy guard owns decisions and validation only, not mutation.
- Verification runtime owns validation and reports only, not application.
- System boot owns construction and wiring, not ongoing mutation.

### Governed Mutation Rules

Any operation that changes runtime state, task state, queue state, files, patches, repair transactions, recovery state, evidence records, or execution lifecycle must pass through all applicable controls:

- policy;
- guard;
- approval when risk or workflow requires it;
- rollback plan when files or runtime state may change;
- verification before final success is recorded;
- audit/evidence for request, decision, execution, rollback, verification, and final status.

Direct mutation is forbidden for external layers even when they can construct valid-looking payloads.

| Operation | Required route | Required controls |
| --- | --- | --- |
| Task create/submit/cancel/pause/resume | `runtime.tasks.*` | scheduler ownership, lifecycle policy, evidence |
| Queue enqueue/dequeue/worker release | scheduler-owned wrapper only | dependency checks, worker routing, evidence |
| Task tick/dispatch/finalize | `runtime.tick()` or owned scheduler loop | scheduler dispatch gate, result validation, evidence |
| Step execution | guarded execution wrapper | execution guard, path/command policy, result normalization, evidence |
| File write or patch | governed mutation or repair route | approval, sandbox, rollback, verification, evidence |
| Repair proposal | repair proposal wrapper | proposal-only semantics, no authorization |
| Repair transaction review | repair review wrapper | authenticated approval/rejection, transaction state validation |
| Repair injection/execution | governed repair route | scope gate, idempotency, replay safety, persistence coordination, evidence |
| Replay | read-only replay wrappers | readonly guard, deterministic validation, no queue/retry mutation |
| Recovery | future recovery wrapper | dry-run, approval, rollback, verification, evidence |
| Evidence write | boot-owned adapter or evidence wrapper | provenance, schema validation, monotonic audit sequence |
| Override | future admin/internal recovery wrapper only | explicit policy, approval, rollback when possible, mandatory evidence |

## Layer Authority Matrix

| Layer | Read | Request | Mutate | Approve | Rollback | Replay | Repair | Recover | Patch | Override | Contract |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `plugin` | `read_only` | `request_only` | none direct | none direct | none direct | read-only | proposal/request only | request only | none direct | none | Use public wrappers only. |
| `capability_pack` | `read_only` | `request_only` | none direct | none direct | none direct | read-only | proposal/request only | request only | none direct | none | Describe operation intent; dispatcher/gates execute. |
| `UI` | `read_only` | `request_only` | none direct | through review wrapper | none direct | read-only | proposal/review only | request only | none direct | none | Render state and submit authenticated decisions. |
| `remote_orchestration` | `read_only` | `request_only` | none direct | authenticated review wrapper | none direct | read-only | governed request only | governed request only | none direct | admin-only future | Requires identity, workspace scope, and audit evidence. |
| `agent_loop` | `read_only` | `request_only` | via scheduler/gateway only | none direct | none direct | read-only | governed request only | request only | none direct | none | Asks runtime owners; does not touch internals. |
| `planner` | `read_only` | `request_only` | none | none | none | none | proposal only | none | none | none | Produces plans/proposals, never authorization. |
| `scheduler_facade` | public read | lifecycle request owner | controlled lifecycle only | forwards review | delegated only | read-only views | governed bridge | request only | none direct | none | Future facade over scheduler public lifecycle. |
| `scheduler_internal` | full owned read | queue/tick owner | queue/status coordination | forwards bindings | queue/worker cleanup only | retry/replay coordination | compatibility repair coordination | no recovery execution | no patch authority | limited compatibility | Internal coordinator, not external authority. |
| `mutation_runtime` | own state | governed requests | `governed_mutation` | consumes approval | `rollback_authority` | mutation audit/replay | repair mutation via governed route | none broad | `patch_authority` | none general | Owns mutation pipeline execution. |
| `repair_runtime` | repair state | repair requests | governed repair only | review/confirmation wrapper | via mutation/recovery | repair replay readonly | `governed_mutation` repair authority | request recovery | through mutation runtime | none direct | Owns repair governance behind wrappers. |
| `recovery_runtime` | recovery state | recovery requests | governed recovery only | may require approval | `rollback_authority` | replay validation | may request repair | `recovery_authority` | through mutation runtime | limited audited override | Recovery must be controlled and evidenced. |
| `policy_guard` | policy inputs | validation requests | none | none | none | none | none | none | none | none | Decisions only; no execution authority. |
| `verification_runtime` | artifacts/results | verification requests | report artifacts only | none | none | replay verification | verifies repair | verifies recovery | none | none | Pass/fail/report only; no application. |
| `system_boot` | bootstrap read | constructs owners | initialization only | none | none | none | none | none | none | none | Wires owners and evidence adapters. |

## Scheduler Isolation Contract

`scheduler.py` is not the public runtime API.

Scheduler internals may coordinate execution, replay continuation, queue ownership, persistence timing, and compatibility bindings, but they must not become external mutation authority. Future runtime access must go through governed public wrappers rather than direct scheduler imports.

Scheduler must retain:

- scheduler loop and tick ownership;
- actual enqueue primitive execution;
- dispatch/finalize/worker routing ownership;
- task lifecycle persistence coordination;
- runtime evidence timing ownership;
- compatibility monkey-patch bindings;
- legacy queue hygiene and pending repair lifecycle until migrated.

External layers must not call:

- scheduler private queue, retry, replay, repair, persistence, or evidence methods;
- `Scheduler._enqueue_repo_task_if_ready`;
- `Scheduler._sync_runner_result_and_requeue_if_ready`;
- scheduler queue hygiene functions as an external API;
- scheduler repair injection or replay continuation helpers;
- `core.tasks.scheduler_core.*`;
- versioned scheduler `_zero_*` symbols.

Future wrappers may depend on scheduler public lifecycle methods internally. Wrapper consumers should not import or instantiate scheduler internals.

## Self-Edit Runtime Safety Contract

Self-edit runtime must be governed mutation only.

Required self-edit flow:

1. Agent or planner produces a proposal.
2. Runtime classifies the proposal as governed mutation or governed repair.
3. Public wrapper submits the request to mutation or repair authority.
4. Policy and scope guard validate operation intent, workspace roots, and target files.
5. Approval or confirmation is required for repository-changing or high-risk edits.
6. Mutation runtime prepares sandbox and rollback plan.
7. Verification runtime defines required checks.
8. Mutation runtime applies patch/write only inside governed execution.
9. Runtime evidence records proposal, policy, approval, mutation, rollback refs, verification, and final status.
10. Scheduler is notified only through public lifecycle, queue, or tick surfaces when orchestration is required.

Self-edit runtime must not directly import or call:

- `StepExecutor` or step handlers;
- mutation pipeline internals;
- patch apply primitives;
- repair transaction lifecycle internals;
- repair injector internals;
- scheduler private enqueue/retry/repair methods;
- direct runtime state file writes;
- direct repository writes outside governed mutation;
- evidence emitters outside owned evidence service;
- forged approval payloads.

Rollback, verification, and audit/evidence are mandatory for repository-changing self-edit operations.

## Future Enforcement Strategy

Future enforcement should make this contract mechanically checkable.

### Import Boundary Tests

Add tests or lint rules preventing external layers from importing:

- `core.tasks.scheduler_core`
- `core.runtime.step_handlers`
- `core.runtime.mutation_runtime_pipeline`
- `core.runtime.mutation_patch_apply`
- `core.runtime.repair_transaction_execution_bridge`
- `core.tasks.runtime_repair_transaction`
- `core.runtime.runtime_execution_transaction`
- `core.runtime.runtime_transaction_orchestrator`
- `core.runtime.runtime_recovery*`
- versioned `_zero_*` symbols.

### Authority Annotations

Add module-level or symbol-level metadata in a future pass:

- `read_only`
- `request_only`
- `governed_mutation`
- `approval_authority`
- `rollback_authority`
- `replay_authority`
- `recovery_authority`
- `patch_authority`
- `override_authority`
- `forbidden_direct_access`

Annotations should start as documentation/metadata and later become enforcement inputs.

### Runtime Permission Checks

Future public wrappers should validate:

- caller identity;
- caller layer;
- workspace scope;
- operation type;
- risk level;
- readonly/replay/audit mode;
- required approval;
- runtime owner;
- evidence requirements.

### Audit Enforcement

Mutating operations should require audit fields:

- request id;
- caller id and layer;
- task id or runtime object id;
- operation and risk;
- policy decision;
- guard decision;
- approval id when required;
- rollback id when applicable;
- verification id/checks;
- replay/audit refs when applicable;
- final status.

### Policy Gate Enforcement

Policy gates should enforce:

- plugins and capability packs are request-only by default;
- UI and remote orchestration cannot mutate directly;
- planner output is proposal-only;
- agent loop cannot directly execute mutation internals;
- scheduler private methods are not external API;
- mutation and repair execution require governed gateways;
- recovery requires recovery-specific policy and evidence;
- readonly runtime modes cannot transition into execution or mutation.

## Runtime Kernel Freeze Direction

### Stabilize Next

The next stable public boundary should be a small runtime facade over:

- boot and health;
- task create/submit/lifecycle;
- tick/run-until-idle;
- queue snapshots;
- planning and proposal generation;
- capability resolve/dispatch;
- governed mutation;
- governed repair review/execution;
- status, timeline, replay, audit, events, traces, and evidence reads.

### Remain Internal

The following should remain internal even after wrappers exist:

- `scheduler_core` helpers;
- scheduler private mutation methods;
- `TaskRuntime` write/transition methods;
- `TaskRunner` tick internals;
- `StepExecutor` and concrete step handlers;
- mutation pipeline, sandbox, patch apply, and approval internals;
- repair injection, transaction lifecycle, apply, rollback, and replay continuation internals;
- recovery execution internals;
- runtime transaction commit/rollback primitives;
- queue/dispatcher/worker primitives;
- evidence adapters and emitters.

### Never Expose Publicly

The following must never become public runtime APIs:

- versioned `_zero_*` compatibility functions;
- scheduler monkey-patch binding functions;
- direct patch apply primitives;
- direct step handler execution;
- direct runtime state file writes;
- direct queue primitive mutation;
- direct repair injection execution;
- direct transaction commit/rollback internals;
- direct evidence forging/emission from external layers.

## Phase 4-C Completion Criteria

Phase 4-C is complete when:

- runtime surfaces are classified into public, internal mutation, and compatibility legacy surfaces;
- proposed public access names and wrapper requirements are documented;
- mutation authority categories and layer authority matrix are defined;
- scheduler isolation is explicitly contracted;
- self-edit runtime safety requirements are explicit;
- future enforcement candidates are documented;
- the runtime kernel freeze direction is stated;
- no runtime implementation, scheduler refactor, behavior change, or file move is introduced by this contract.

## Non-Goals

This contract does not:

- implement `zero.runtime` or `core.runtime.kernel_api`;
- implement wrappers;
- create runtime APIs;
- refactor `scheduler.py`;
- move files;
- change imports or exports;
- change runtime behavior;
- change tests;
- approve external access to internal mutation surfaces;
- implement HTTP, RPC, CLI, or UI endpoints.
