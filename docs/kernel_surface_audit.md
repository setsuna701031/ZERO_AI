# Kernel Surface Audit - Phase 4-C

Date: 2026-05-18

Scope scanned:

- `core/runtime/`
- `core/tasks/`
- `core/agent/`
- `core/planning/`
- `services/system_boot.py`

This audit is documentation-only. It does not refactor `scheduler.py`, move files, change runtime behavior, or modify tests.

## Summary

The current ZERO runtime kernel has several real public entrypoints, but many importable classes and functions are mutation-bearing internals. The safest external-facing surface today is the boot/system facade, scheduler/task lifecycle facade, governed mutation gateway, planner/execution gateway adapters, runtime evidence query/serialization APIs, and read-only snapshot/report builders.

External callers, plugins, UI code, remote orchestration, capability packs, and future agents should not call low-level mutation, queue, step handler, runtime-state, repair injection, transaction lifecycle, or compatibility monkey-patch surfaces directly. Those surfaces should remain behind scheduler, TaskRunner/TaskRuntime, governed repair APIs, mutation gateways, and runtime capability dispatchers.

## PUBLIC_RUNTIME_SURFACE

Stable or intended external-facing runtime APIs.

| Module path | Symbol | Current purpose | Current users if obvious | Recommended future status | Risk if exposed externally |
| --- | --- | --- | --- | --- | --- |
| `services/system_boot.py` | `boot_system(workspace_dir)` | Constructs a complete ZERO runtime system with repository, scheduler, task runtime, task runner, step executor, evidence adapters, planner, and optional agent loop. | CLI/system launch paths; intended top-level bootstrap. | `keep_public` | Low-medium. Safe as facade, but exposes object graph attributes that can be misused if treated as mutable public API. |
| `services/system_boot.py` | `ZeroSystem` | Boot facade with `tick`, `run_until_idle`, `health`, queue accessors, task delegation helpers. | `boot_system`; likely app/UI orchestration. | `keep_public` | Medium. Public methods are useful; direct access to internals such as `.scheduler` or `.task_runtime` can bypass intended boundaries. |
| `core/tasks/scheduler.py` | `Scheduler` public methods (`create_task`, `submit_task`, `submit_existing_task`, `tick`, `run_once`, `run_next`, queue views) | Owns scheduler loop, queue/dispatch ownership, task lifecycle persistence, compatibility bindings, and evidence timing. | `services/system_boot`, `run_scheduler.py`, tests, smoke scripts, agent loop task mode. | `keep_public` with a narrower facade later | High if external code calls private methods or mutation helpers. Public lifecycle methods are acceptable; private queue/repair methods must stay internal. |
| `core/agent/agent_loop.py` | `AgentLoop.run(user_input)` | User-facing agent loop entry that routes direct, LLM, task, tool, document-flow, and scheduler-backed work. | `services/system_boot`, agent loop smoke tests, likely UI/app. | `keep_public` | Medium-high. It can create tasks and trigger tools; should remain facade-level and policy guarded. |
| `core/planning/planner.py` | `Planner.plan(...)` | Deterministic planning API that converts user/task input into step payloads. | `services/system_boot`, scheduler, agent loop, tests. | `keep_public` | Medium. Plans may include side-effect steps; callers should route through scheduler/execution guard rather than executing plans directly. |
| `core/planning/task_replanner.py` | `TaskReplanner` | Replanning adapter used by boot and task runner/scheduler flows. | `services/system_boot`; scheduler/task runner context. | `keep_public` or `needs_wrapper` | Medium. Replan output can influence mutation/retry behavior; should be exposed as proposal/decision, not direct execution. |
| `core/planning/planner_runtime_entry.py` | `run_planner_runtime_entry`, `export_planner_runtime_payload` | Contract-normalizing planner runtime entry. | Gateway/runtime tests; intended adapter surface. | `keep_public` | Low-medium. Safe normalization layer; risk is accepting untrusted planner output without downstream guard. |
| `core/tasks/planner_gateway_runtime.py` | `run_scheduler_planner_gateway`, `export_scheduler_runtime_planner_payload` | Scheduler-safe planner gateway with legacy fallback and normalized payload. | `core/tasks/scheduler.py`. | `keep_public` | Low-medium. Good wrapper; callers should still not execute returned steps directly. |
| `core/tasks/execution_runtime_entry.py` | `run_execution_runtime_entry`, `export_execution_runtime_result` | Contract-normalizing execution entry around an executor object. | Gateway tests; future runtime adapters. | `keep_public` | Medium. Can execute side effects through supplied executor; only safe with governed executor and guard. |
| `core/tasks/scheduler_execution_gateway.py` | `run_scheduler_step_execution_gateway`, `SchedulerExecutionGatewayResult` | Scheduler step execution gateway result wrapper. | Scheduler execution gateway tests and scheduler integration. | `keep_public`/`needs_wrapper` | Medium-high. Must preserve guard and scheduler context; direct external use can bypass queue/task ownership. |
| `core/runtime/mutation_gateway.py` | `MutationGatewayRequest`, `run_governed_mutation` | Single public governed mutation execution gateway. | Governed repair and mutation pipeline consumers. | `keep_public` | High but appropriate. It intentionally gates high-risk mutation; exposing lower layers instead would be unsafe. |
| `core/runtime/governed_repair_api.py` | `execute_governed_repair_mutation` | Public governed repair API wrapping transaction creation, staging, commit, and execution bridge. | Governed repair mutation step handler/API users. | `keep_public` | High but controlled. External callers must provide scope, roots, approval/verification parameters. |
| `core/runtime/runtime_capability_dispatcher.py` | `RuntimeCapabilityDispatcher.dispatch`, `dispatch_many` | Operation-level capability dispatch through resolver and intent gate router. | Capability dispatcher tests; future capability packs. | `keep_public` | Medium-high. Should be the public capability route, but only with registered operations and gate integration. |
| `core/runtime/runtime_capability_resolver.py` | `RuntimeCapabilityResolver.resolve`, `resolve_many` | Maps operation names to runtime capability metadata. | Dispatcher/tests. | `keep_public` | Low-medium. Metadata only, but incorrect custom registries can misclassify risk. |
| `core/runtime/runtime_operation_registry.py` | `RuntimeOperationRegistry` | Registry for supported runtime operations, risk levels, and governance targets. | Capability resolver/tests. | `keep_public` with governance | Medium. Custom operation registration can create unsafe routes if not governed. |
| `core/runtime/runtime_boundary.py` | `RuntimeBoundary` request methods | Ownership/mutation boundary requests for queue, execution result, dispatch, snapshot, event, incident. | Boundary tests/future integrations. | `keep_public` | Medium. Intended guard surface; bypassing it is the risk, not using it. |
| `core/runtime/runtime_transition_policy.py` | `RuntimeTransitionPolicy.check_transition` | Runtime transition legality policy, including readonly replay/audit rules and terminal/retry restrictions. | `TaskRuntime`, transition policy tests. | `keep_public` | Medium. External callers should use it for validation, not treat approval as persistence. |
| `core/runtime/runtime_orchestrator.py` | `RuntimeOrchestrator.evaluate_runtime`, `should_trigger_recovery` | Monitor/recovery/snapshot/state orchestrator for runtime health. | Runtime orchestrator tests/tools. | `keep_public` | Medium. Read/decision surface; recovery triggering must still be governed. |
| `core/runtime/runtime_mainline_evidence_seal.py` | `build_runtime_mainline_evidence_seal`, `RuntimeMainlineEvidenceSeal` | Builds scheduler/task/step evidence boundaries/adapters and baseline evidence refs. | `services/system_boot`. | `keep_public` | Low-medium. Safe as setup facade; direct manipulation of adapters can confuse audit trails. |
| `core/runtime/trace_runtime.py` | `TraceRuntime`, `build_trace_runtime` | Trace load/save/status runtime for scheduler trace integration. | Scheduler, trace tests. | `keep_public` | Low-medium. Trace writes can affect observability but not execution semantics directly. |
| `core/runtime/event_sink.py` | `RuntimeEventSink` | Runtime event persistence sink. | Event/replay tests and tooling. | `keep_public` | Low-medium. Can pollute event logs if externally writable without namespace controls. |
| `core/runtime/event_replay.py` | `RuntimeEventReplay` | Read-only replay/filter/timeline over event logs. | Event replay tests/tools. | `keep_public` | Low. Read-only if file access is controlled. |
| `core/runtime/event_stream.py` | `RuntimeEventChannel`, `attach_runtime_event_stream`, stream merge/build helpers | Event stream envelope and adapter utilities. | Runtime event integration tools/tests. | `keep_public` | Low-medium. Mostly metadata; bad streams can mislead observability. |
| `core/tasks/runtime_kernel_status.py` | `build_runtime_kernel_status`, `format_runtime_kernel_status`, task variants | Read-only kernel status formatting/builders. | `app.py`, display/UI. | `keep_public` | Low. Display/reporting only. |
| `core/tasks/runtime_kernel_timeline.py` | `build_runtime_timeline`, timeline summary helpers | Read-only timeline normalization and summary. | Kernel status/report flows. | `keep_public` | Low. Display/reporting only. |
| `core/tasks/runtime_kernel_events.py` | Runtime kernel event builders/helpers | Read-only event formatting for kernel status. | Status/timeline layers. | `keep_public` | Low. Display/reporting only. |
| `core/tasks/runtime_replay_snapshot.py` | `build_runtime_replay_snapshot` | Read-only runtime replay snapshot builder. | `app.py`, display tests. | `keep_public` | Low. Snapshot accuracy matters, but no mutation. |
| `core/tasks/runtime_replay_narrative.py` | `build_runtime_replay_narrative` | Read-only narrative over replay snapshots. | Display/runtime audit. | `keep_public` | Low. |
| `core/tasks/runtime_audit_artifact.py` | `build_runtime_audit_artifact` | Read-only audit artifact from snapshot/narrative. | Runtime audit/display. | `keep_public` | Low. |
| `core/tasks/runtime_audit_registry.py` | Runtime audit registry builders | Audit registry/report construction. | Audit tests. | `keep_public` | Low-medium. Wrong registration can confuse audit provenance. |
| `core/tasks/runtime_repair_contract.py` | `build_runtime_repair_contract` | Read-only repair contract builder. | `app.py`, repair UI/reporting. | `keep_public` | Low-medium. Should remain descriptive, not executable. |
| `core/tasks/runtime_repair_envelope.py` | `build_runtime_repair_envelope` | Read-only repair envelope builder. | `app.py`. | `keep_public` | Low-medium. |
| `core/tasks/runtime_repair_planner_bridge.py` | `build_runtime_repair_planner_bridge` | Planner bridge/report payload for repair proposals. | `app.py`, repair planner flow. | `keep_public`/`needs_wrapper` | Medium. Should remain proposal-only unless wrapped by governed repair execution. |
| `core/tasks/runtime_repair_planner_proposal.py` | `build_runtime_repair_planner_proposal` | Builds repair planner proposal payload. | `app.py`. | `keep_public`/`needs_wrapper` | Medium. Proposal can be mistaken for authorization. |
| `core/tasks/runtime_repair_confirmation.py` | `build_runtime_repair_confirmation_gate` | Review/confirmation gate payload. | `app.py`, transaction review. | `keep_public` | Low-medium. Approval must be routed through transaction review actions. |
| `core/tasks/runtime_repair_suggestion.py` | `build_runtime_repair_suggestion` | Suggestion/report payload for repair UI. | `app.py`, display. | `keep_public` | Low. |
| `core/tasks/runtime_repair_transaction_review.py` | `build_runtime_repair_transaction_review`, approve/reject review functions | Review-layer contract and approval/rejection action over transactions. | Scheduler review bindings. | `keep_public`/`needs_wrapper` | Medium-high. Approval changes transaction lifecycle; must remain behind review/auth controls. |
| `core/tasks/task_repository.py` | `TaskRepository` | Task index persistence and DAG status helpers. | Scheduler, boot, scripts/tests. | `keep_public` with constrained use | Medium. Direct external writes can bypass scheduler lifecycle/evidence. |
| `core/tasks/task_paths.py` | `TaskPathManager` | Workspace/task/shared path resolution. | Boot, repository, step executor, scheduler. | `keep_public` | Medium. Path resolution must not be confused with authorization. |
| `core/tasks/task_workspace.py` | `TaskWorkspace` | Task workspace artifact helper. | Scheduler/boot. | `keep_public` | Low-medium. Can create/read task artifacts. |
| `core/tasks/task_models.py` | Task model dataclasses/types | Stable task payload shapes. | Task layers/tests. | `keep_public` | Low. |
| `core/tasks/task_state.py` | Task state helpers/types | Task status/state modeling. | Task layers/tests. | `keep_public` | Low. |
| `core/planning/planner_contract.py` | Planner contract normalization/validation functions | Public planner payload contract. | Planner gateway/tests. | `keep_public` | Low-medium. Should validate, not execute. |
| `core/planning/planner_contract_adapter.py` | Planner adapter/export helpers | Adapter from raw planner result to runtime-safe payload. | Planner runtime entry. | `keep_public` | Low. |
| `core/planning/replan_suggestion.py` | Replan suggestion builders/formatter | UI/CLI friendly replan suggestions. | Scheduler, app, UI bridge. | `keep_public` | Low. |
| `core/agent/agent_route_policy.py` | Document/task route policy helpers | Route classification helpers for AgentLoop. | AgentLoop, smoke tests. | `keep_public` | Low-medium. Policy-only; should not execute. |
| `core/agent/loop_decision.py` | `observe_and_decide`, decision dataclasses | Agent loop observation-to-action decision. | AgentLoop. | `keep_public`/`needs_wrapper` | Medium. Decisions can drive retries/continuation; callers should not mutate runtime directly from it. |
| `core/agent/model_use_policy.py` | Model-use classification helpers | Policy hints for model/tool choice. | Agent/UI layers. | `keep_public` | Low. |

## INTERNAL_MUTATION_SURFACE

Internal-only mutation/state/execution surfaces that plugins, capability packs, UI, remote orchestration, and future agents must not call directly.

| Module path | Symbol | Current purpose | Current users if obvious | Recommended future status | Risk if exposed externally |
| --- | --- | --- | --- | --- | --- |
| `core/runtime/task_runtime.py` | `TaskRuntime` mutation methods (`ensure_runtime_state`, `save_runtime_state`, `mark_running`, `advance_step`, `record_step_failure`, `mark_failed`, `mark_finished`, repair/action methods) | Owns runtime state file lifecycle and task/runtime state transitions. | `TaskRunner`, `Scheduler`, boot, tests. | `internal_only` behind scheduler/runner | High. Direct calls can corrupt state, bypass scheduler evidence, reopen terminal tasks, or break replay idempotency. |
| `core/runtime/task_runner.py` | `TaskRunner.run_task_tick`, `run_one_step`, repair injection/retry internals | Executes a task tick, calls StepExecutor, advances TaskRuntime, handles repair/retry/replan. | Scheduler v733 bridge, AgentLoop, boot, tests. | `internal_only`/`needs_wrapper` | High. Direct external calls can execute side effects outside scheduler queue ownership. |
| `core/runtime/step_executor.py` | `StepExecutor.execute`, `execute_step`, handler registry | Executes individual step payloads, including command/write/apply_patch/repair handlers. | TaskRunner, scheduler simple path, boot, tests. | `internal_only` for remote/plugins; public only through guarded wrapper | Critical. Direct calls can run commands, write files, apply patches, or bypass queue/task lifecycle. |
| `core/runtime/step_handlers.py` | `CommandStepHandler`, `RunPythonStepHandler`, `WriteFileStepHandler`, `ApplyUnifiedDiffStepHandler`, `GovernedRepairMutationStepHandler`, etc. | Concrete step side-effect handlers. | `StepExecutor`. | `internal_only` | Critical. Direct handler calls bypass executor normalization, evidence, and guard context. |
| `core/tasks/execution_guard.py` | `ExecutionGuard.check_step` | Path/command/runtime-mode policy guard. | Scheduler simple execution path. | `internal_only` or policy service | High. A guard decision is not execution authorization by itself; external misuse can create false safety. |
| `core/tasks/scheduler_core/*` | dispatch, queue, replay, repair injection, repo state, simple runner helpers | Scheduler implementation helpers and mutation orchestration. | `Scheduler` only, tests. | `internal_only` | High. Helpers assume scheduler context and can bypass public lifecycle/evidence if called directly. |
| `core/tasks/scheduler_core/repair_injection_execution.py` | `execute_repair_injection_transaction`, `normalize_repair_injection_mutation` | Mutation execution and packaging for repair injection after Phase 3. | v734 scheduler bridge. | `internal_only` | High. Direct calls mutate steps/runtime state/persistence without scheduler ownership. |
| `core/tasks/scheduler_core/repair_replay_continuation.py` | continuation builders | Post-injection continuation packaging and enqueue intent. | v734 scheduler bridge. | `internal_only` | High. Direct use can create queued replay state without actual queue ownership. |
| `core/tasks/scheduler_core/retrying_repair_replay_state.py` | replay decision/state helpers | Determines retry repair replay state from task/runtime state. | v734 scheduler bridge. | `internal_only` | Medium-high. Exposing can encourage direct replay orchestration. |
| `core/tasks/scheduler_core/code_chain_tick_replay_bridge.py` | v733 bridge helper | Builds compatibility bridge to TaskRunner for Code Chain workflow ticks. | Scheduler v733 binding. | `internal_only` | High. Binding order and runtime handoff are scheduler-owned. |
| `core/runtime/repair_step_injector.py` | `RepairStepInjector.inject_steps_into_state`, `build_injection` | Builds and injects repair steps into runtime state. | TaskRunner repair flow; repair tests. | `internal_only` except proposal builder wrapper | High. Direct injection can violate readonly replay/audit modes or duplicate repair steps. |
| `core/runtime/repair_planner.py` | `RepairPlanner` | Builds repair plans from failures. | TaskRunner. | `internal_only`/`needs_wrapper` | Medium-high. Plans must remain proposals until governed and injected through runtime owner. |
| `core/runtime/repair_rollback.py` | rollback helpers | Repair backup/rollback decisions and restore helpers. | TaskRunner repair flow. | `internal_only` | High. Direct rollback can overwrite files/state unexpectedly. |
| `core/runtime/repair_transaction_execution_bridge.py` | `execute_committed_runtime_repair_transaction` | Executes committed repair transactions through mutation pipeline. | `governed_repair_api`. | `internal_only` | Critical. Must only run after transaction authorization/commit. |
| `core/tasks/runtime_repair_transaction.py` | transaction create/stage/commit/lifecycle functions | Runtime repair transaction lifecycle. | Governed repair API, review. | `internal_only` with review wrapper | High. Direct commit/stage can bypass confirmation UI/policy. |
| `core/tasks/runtime_repair_apply_transaction.py` | repair apply transaction helpers | Applies runtime repair transaction. | Repair apply executor/control flows. | `internal_only` | Critical. Mutation execution surface. |
| `core/tasks/runtime_repair_controlled_apply.py` | controlled repair apply helpers | Controlled application of repair mutations. | Repair apply flows. | `internal_only` | Critical. |
| `core/tasks/runtime_repair_mutation_authorization.py` | authorization builders/checks | Authorizes repair mutation scope. | Repair governance flow. | `internal_only`/`needs_wrapper` | High. External callers could forge authorization if not wrapped. |
| `core/tasks/runtime_repair_mutation_scope_gate.py` | scope gate builders/checks | Controls repair mutation scope. | Repair governance flow. | `internal_only`/`needs_wrapper` | High. |
| `core/tasks/runtime_repair_governance_boundary.py` | repair governance boundary builders | Describes boundary summaries. | Repair reporting/governance. | `needs_wrapper` | Medium. Mostly descriptive but can be confused with authorization. |
| `core/runtime/mutation_runtime_pipeline.py` | `run_mutation_runtime_pipeline` | Full mutation session/sandbox/approval/verification/apply pipeline. | `mutation_gateway`. | `internal_only` | Critical. Public callers should use `run_governed_mutation`. |
| `core/runtime/mutation_session.py` | mutation session creation/enums | Mutation session state and policy data. | Mutation gateway/pipeline. | `internal_only` except enum types | High. Session creation alone is not authorization. |
| `core/runtime/mutation_sandbox.py` | sandbox preparation/execution helpers | Prepares mutation sandbox. | Mutation pipeline. | `internal_only` | High. Direct sandbox changes can desync rollback/evidence. |
| `core/runtime/mutation_patch_apply.py` | patch apply primitives | Applies patch/mutation changes. | Mutation pipeline. | `internal_only` | Critical. Direct file mutation bypasses approvals/rollback. |
| `core/runtime/mutation_approval.py` | approval decision types/helpers | Approval modeling for mutation pipeline. | Mutation gateway/pipeline. | `internal_only`/`needs_wrapper` | High. Approval data must be tied to authenticated operator/context. |
| `core/runtime/mutation_verification.py` | mutation verification helpers | Verifies mutation results. | Mutation pipeline. | `internal_only` | High. Direct verification without pipeline can create false pass/fail. |
| `core/runtime/mutation_replay.py` | mutation replay timeline read/write | Mutation replay audit/reconstruction. | Mutation tests/audit. | `internal_only` or read-only wrapper | Medium-high. Writing replay timelines externally can poison audit. |
| `core/runtime/runtime_execution_transaction.py` | transaction manager/classes | Low-level runtime execution transaction begin/run/commit/rollback. | Transaction orchestrator tests. | `internal_only` | Critical. Direct commit/rollback bypasses capability/gate layers. |
| `core/runtime/runtime_transaction_orchestrator.py` | `RuntimeTransactionOrchestrator` | Groups and runs/commits/rolls back runtime transactions. | Tests/future orchestrators. | `needs_wrapper` | Critical if exposed without operation registry and gate checks. |
| `core/runtime/runtime_plan_executor.py` | runtime plan execution | Executes runtime execution plans. | Recovery/orchestration layers. | `internal_only` | High. |
| `core/runtime/runtime_recovery*.py` | recovery coordinator/policy/gate/approval/dry-run/execution modules | Runtime recovery planning, approval, execution, evidence. | Runtime recovery tests/orchestrator. | `internal_only` with public recovery facade later | High-critical. Recovery can mutate state/files and must remain governed. |
| `core/runtime/runtime_state_registry.py` | `RuntimeStateRegistry` | Runtime state registry and snapshots. | Registry tests. | `internal_only`/`needs_wrapper` | High. Direct writes can conflict with TaskRuntime ownership. |
| `core/runtime/runtime_state_machine.py` | `RuntimeStateMachine` | State transition engine. | `TaskRuntime`. | `internal_only` | High. Use via TaskRuntime/transition policy. |
| `core/runtime/runtime_mutation_guard.py` | `guard_mutation` | Runtime mutation ownership guard. | RuntimeBoundary. | `internal_only` or policy primitive | Medium-high. Should be wrapped by RuntimeBoundary. |
| `core/runtime/runtime_gate_integration.py` | gated lifecycle/replay/recovery integrations | Runtime intent gate to lifecycle/recovery/replay engines. | RuntimeIntentGateRouter. | `internal_only` | High. Gate integrations assume validated operation route. |
| `core/runtime/runtime_replay_engine.py` | `RuntimeReplayEngine` | Replay session/group engine. | Runtime intent router/tests. | `internal_only`/read-only wrapper | Medium-high. Replay should not trigger mutation or state reopen. |
| `core/runtime/execution_gateway.py` | execution gateway classes/functions | Execution gateway between plan/session/executor. | Runtime tests. | `needs_wrapper` | High if it can invoke execution directly. |
| `core/runtime/executor.py` | executor primitives | Runtime execution abstraction. | Internal execution tests/layers. | `internal_only` | High. |
| `core/runtime/execution_session.py` | execution session model | Session lifecycle for execution. | Replay/audit/session layers. | `internal_only` | Medium-high. |
| `core/runtime/execution_session_store.py` | session store | Execution session persistence. | Replay/audit/session layers. | `internal_only` | Medium-high. |
| `core/runtime/execution_replay.py` | execution replay verifier | Replay verification of execution snapshots. | Evidence/audit tests. | `internal_only`/read-only wrapper | Medium. |
| `core/runtime/execution_audit.py` | audit records/trail | Execution audit persistence. | Evidence tests. | `internal_only`/read-only wrapper | Medium. |
| `core/runtime/execution_cycle_runtime.py` | `ExecutionCycleRuntime` | Scheduler execution cycle support. | Scheduler. | `internal_only` | Medium-high. |
| `core/runtime/task_scheduler.py` | `TaskScheduler` | Base queue/task scheduler compatibility class. | `Scheduler` superclass. | `internal_only`/`legacy_compat` | High. External callers should use `core.tasks.scheduler.Scheduler`. |
| `core/runtime/task_queue.py` | `TaskQueue` | Low-level queue primitive. | Runtime/scheduler legacy paths. | `internal_only` | High. Direct queue mutation bypasses scheduler evidence and dependency checks. |
| `core/tasks/scheduler_core/task_scheduler_queue.py` | `TaskSchedulerQueue`, `ScheduledTask` | Scheduler ready queue implementation. | Scheduler/dispatcher. | `internal_only` | High. Direct calls bypass queue transition policy. |
| `core/tasks/scheduler_core/task_dispatcher.py` | `TaskDispatcher` | Worker/queue dispatch implementation. | Scheduler. | `internal_only` | High. Direct dispatch bypasses scheduler lifecycle/evidence. |
| `core/tasks/scheduler_core/worker_pool.py` | `WorkerPool` | Running worker slot tracking. | Scheduler/dispatcher. | `internal_only` | High. Direct worker mutation can leak/release slots incorrectly. |
| `core/tasks/task_storage.py` | task storage helpers | Lower-level task artifact/index IO. | Task repository/workspace layers. | `internal_only` | Medium-high. Direct writes can bypass repository normalization. |
| `core/tasks/simple_step_runner.py` | simple step runner | Legacy/simple execution loop. | Scheduler/simple tests. | `internal_only`/`legacy_compat` | High. Can execute steps without full scheduler lifecycle. |
| `core/tasks/task_scheduler_loop.py` | scheduler loop wrapper/thread helpers | Task scheduler loop. | System loop integration. | `internal_only`/`needs_wrapper` | Medium-high. |
| `core/tasks/scheduler_thread.py` | `SchedulerThread` | Background scheduler thread wrapper. | `run_zero_system.py`. | `needs_wrapper` | Medium. Threaded scheduling needs lifecycle controls. |
| `core/agent/capability_invoker.py` | `execute_resolved_capability` | Executes resolved agent capability. | TaskRunner/AgentLoop capability paths. | `internal_only`/`needs_wrapper` | High. Direct capability execution can bypass route/gate policy. |
| `core/agent/agent_component_invoker.py` | component call helpers | Invokes router/planner/step executor/verifier/safety guard components. | AgentLoop. | `internal_only` | Medium-high. Direct calls bypass AgentLoop normalization. |
| `core/agent/repo_edit_review_adapter.py` | `run_agent_repo_edit_review` | Agent repo-edit review bridge. | Agent/self-edit route. | `internal_only`/`needs_wrapper` | High. Repo edit decisions must be governed. |
| `core/agent/local_observer.py` | observe result helpers | Normalizes local result observations. | AgentLoop/decision layer. | `internal_only` except read-only diagnostics | Low-medium. |
| `core/agent/document_flow_trace_writer.py` | trace writer helpers | Writes document-flow trace artifacts. | AgentLoop. | `internal_only` | Medium. External writes can pollute traces. |
| `core/runtime/scheduler_evidence_adapter.py` | `SchedulerEvidenceAdapter` | Adapter from scheduler events to evidence boundary. | Boot/scheduler. | `internal_only` | Medium. Direct event emission can falsify audit trail. |
| `core/runtime/task_runtime_evidence_adapter.py` | `TaskRuntimeEvidenceAdapter` | Adapter from TaskRuntime events to evidence boundary. | Boot/TaskRuntime. | `internal_only` | Medium. |
| `core/runtime/step_executor_evidence_adapter.py` | `StepExecutorEvidenceAdapter` | Adapter from StepExecutor events to evidence hook. | Boot/StepExecutor. | `internal_only` | Medium. |
| `core/runtime/runtime_evidence_persistence.py` | evidence persistence | Persists runtime evidence bundles/records. | Evidence integration. | `internal_only`/read-only wrapper | Medium-high. Direct writes can poison audit. |
| `core/runtime/runtime_evidence_registry.py` | evidence registry | Evidence bundle registry. | Evidence layers/tests. | `internal_only`/read-only wrapper | Medium-high. |
| `core/runtime/runtime_evidence_integration.py` | `RuntimeEvidenceEmitter` | Emits runtime evidence records. | Mainline evidence seal. | `internal_only` | Medium-high. Direct emission can fake evidence sequence. |

## COMPATIBILITY_LEGACY_SURFACE

Legacy compatibility surfaces kept only to avoid breaking current flows.

| Module path | Symbol | Current purpose | Current users if obvious | Recommended future status | Risk if exposed externally |
| --- | --- | --- | --- | --- | --- |
| `core/tasks/scheduler.py` | Versioned `_zero_v7xx/_zero_v3xx` monkey-patch functions and `Scheduler.* = ...` bindings | Preserve scheduler behavior across staged extraction: repair step preservation, repairable allowlists, v724 hygiene, v726 pending lock lifecycle, v733 Code Chain bridge, v734 retry bridge, final result enrichment. | Scheduler import side effects; tests and current runtime flows. | `legacy_compat` | High. External callers should never call these symbols; binding order is behavior-critical. |
| `core/runtime/step_executor.py` | Versioned `_zero_v7xx/_zero_v8xx` monkey-patch handlers and registration functions | Preserve Code Chain repair, syntax repair, multi-patch, apply handlers, and handler registration behavior. | StepExecutor import/init side effects. | `legacy_compat` | Critical. Direct calls bypass handler registry and safety context. |
| `core/runtime/task_runner.py` | Versioned `_zero_v7xx/_zero_v8xx/_zero_v9xx` monkey-patch functions | Preserve retry/replan/failure/action landing behavior. | TaskRunner import side effects and scheduler bridge. | `legacy_compat` | High-critical. Direct calls can mutate runtime state outside normal tick flow. |
| `core/runtime/task_runtime.py` | Versioned `_zero_v8xx/_zero_v9xx` monkey-patch functions | Preserve engineering session/action landing, repair context normalization, runtime-state save/advance/failure/finish behavior. | TaskRuntime import side effects. | `legacy_compat` | High. Direct calls can corrupt runtime state and bypass transition policy. |
| `core/planning/planner.py` | Versioned `_zero_v7xx` planner route/repair functions | Preserve autonomous repair and Code Chain diff routing behavior. | Planner import side effects. | `legacy_compat` | Medium-high. Direct use can generate unsupported repair plans. |
| `core/runtime/task_scheduler.py` | `TaskScheduler` | Earlier/basic scheduler base class retained under `core.runtime`. | `core.tasks.scheduler.Scheduler` superclass; older tests. | `legacy_compat` | High if used externally instead of current Scheduler; lacks newer ownership/evidence semantics. |
| `core/agent/router_backup.py` | `SimpleRouter`, `Router` | Backup/legacy router implementation. | Dynamic resolver fallback in boot may discover router elsewhere; tests may import. | `legacy_compat`/`needs_deprecation` | Medium. Route decisions may not match current policy stack. |
| `core/agent/observe.py` | `observe_world` | Early/simple world observation helper. | `app.py` dynamic import path. | `legacy_compat` | Low-medium. Read-only-ish, but not a full runtime observer. |
| `core/tasks/simple_step_runner.py` | simple runner functions/classes | Older direct step runner path. | Scheduler/simple tests. | `legacy_compat` | High. External use bypasses current TaskRunner/TaskRuntime integration. |
| `core/tasks/execution_gateway.py` and `core/tasks/execution_contract*.py` | execution contract/gateway helpers | Staged compatibility for execution contract normalization. | Execution gateway runtime/tests. | `legacy_compat`/`needs_wrapper` | Medium-high. Prefer `execution_runtime_entry` or scheduler gateway wrapper. |
| `core/tasks/planner_gateway.py` and `core/planning/planner_contract*.py` | planner gateway/contract helpers | Staged planner contract compatibility. | Planner gateway runtime/tests. | `legacy_compat` plus public contract pieces | Medium. Use runtime wrapper for scheduler-facing calls. |
| `core/tasks/runtime_repair_confirmation_actions.py` | approve/reject confirmation helpers | Legacy/current confirmation action implementation. | Transaction review. | `legacy_compat` behind review API | Medium-high. Direct approval helper calls can skip review context. |
| `core/tasks/runtime_repair_replay_queue.py` | repair replay queue helpers | Replay queue support for repair runtime. | Repair replay tests/flows. | `legacy_compat`/`internal_only` | High. Direct use can desync replay queue state. |
| `core/runtime/controlled_mutation_*.py` | controlled mutation boundary/sandbox/verification/rollback modules | Earlier controlled mutation layer alongside newer mutation gateway/pipeline. | Controlled mutation tests/legacy flows. | `legacy_compat`/`needs_deprecation` | High-critical. Duplicate mutation pathway increases policy drift risk. |
| `core/runtime/repair_transaction_gateway_adapter.py` | repair transaction adapter | Adapter between repair transactions and runtime mutation gateway. | Repair transaction bridge. | `legacy_compat`/`internal_only` | High. External use bypasses governed repair API. |
| `core/runtime/runtime_recovery_trace_adapter.py`, `runtime_recovery_trace_runtime_adapter.py` | recovery trace compatibility adapters | Recovery trace bridge. | Recovery tests/trace flows. | `legacy_compat` | Medium. |
| `core/tasks/runtime_state_hygiene.py` | `freeze_runtime_export`, JSON safety helpers | Compatibility hygiene/freezing for runtime export payloads. | `app.py`, repair review. | `legacy_compat` but useful utility | Low-medium. Should remain read-only/sanitizing. |
| `core/tasks/runtime_repair_apply_executor_contract.py`, `runtime_repair_apply_executor_contract` symbols | Apply executor contract artifacts | Repair apply compatibility contract. | Repair apply tests. | `legacy_compat`/`needs_wrapper` | Medium-high. Contract-only if used correctly; risky if paired with direct apply. |

## Boundary Recommendations

1. Public callers should start at `boot_system`, `ZeroSystem`, `Scheduler` public lifecycle methods, `AgentLoop.run`, `Planner.plan`, planner/execution gateway wrappers, `RuntimeCapabilityDispatcher`, `run_governed_mutation`, or `execute_governed_repair_mutation`.
2. Plugins and future agents must not call `TaskRuntime`, `TaskRunner`, `StepExecutor`, scheduler_core helpers, step handlers, transaction managers, mutation pipeline internals, repair injectors, or queue/worker primitives directly.
3. UI and remote orchestration should use read-only builders for status/timeline/replay/audit and use explicit approval/gateway APIs for mutation.
4. Runtime evidence adapters should be constructed by the evidence seal or boot system. External code should not emit evidence directly except through a future authenticated evidence API.
5. `core.runtime.task_scheduler.TaskScheduler` and versioned `_zero_*` compatibility functions should be treated as legacy implementation details, not runtime kernel APIs.
6. Where a surface is marked `needs_wrapper`, expose it only after a wrapper can enforce identity, workspace scope, approval, transition policy, evidence, and replay/idempotency semantics.

## Highest-Risk External Exposure

- `StepExecutor.execute_step` and concrete `step_handlers`.
- Mutation pipeline internals and patch apply primitives.
- `TaskRuntime.save_runtime_state` and transition methods.
- `TaskRunner.run_task_tick` outside scheduler ownership.
- Scheduler private enqueue/dispatch/repair methods.
- Runtime transaction orchestrator/manager commit and rollback methods.
- Repair step injection and repair transaction execution bridge.
- Compatibility monkey-patch functions in scheduler, step executor, task runner, task runtime, and planner.

## Suggested Near-Term Cleanup

1. Add `__all__` or public surface docs for `core/runtime`, `core/tasks`, `core/agent`, and `core/planning`.
2. Introduce a `core/runtime/kernel_api.py` or similar facade exporting only approved public entrypoints.
3. Mark internal mutation modules with module-level comments or docs in a later docs-only pass.
4. Add import lint/guard tests preventing plugins/UI/capability packs from importing `scheduler_core`, step handlers, mutation pipeline internals, or `_zero_*` compatibility symbols.
5. Deprecate or wrap `core.runtime.task_scheduler.TaskScheduler` so external callers converge on `core.tasks.scheduler.Scheduler` or `ZeroSystem`.
