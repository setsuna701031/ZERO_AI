# Runtime Mainline Freeze Audit - Phase 4-E

Date: 2026-05-18

Source contract and regression nets:

- `docs/runtime_kernel_boundary_contract.md`
- `tests/test_runtime_boundary_imports.py`
- `tests/test_runtime_mutation_authority_boundaries.py`

This audit identifies which ZERO runtime flows are stable enough to become Runtime Kernel contract candidates. It is documentation-only: no scheduler refactor, runtime API implementation, file move, production behavior change, or warning cleanup is part of this phase.

## Summary

The strongest freeze candidates are the governed mutation flow, read-only replay/reporting flow, scheduler facade flow, and boundary enforcement tests themselves. Repair, rollback, recovery, and execution evidence have useful regression coverage, but parts of their execution paths remain internal or transitional because they still depend on compatibility bridges, private scheduler ownership, or future facade/wrapper enforcement.

Classification terms:

- `stable_contract_candidate`: behavior is sufficiently covered and boundary-aligned to be documented as a contract candidate.
- `internal_only`: flow may be stable, but must not be exposed directly outside runtime/tasks ownership.
- `still_transitional`: behavior is useful but depends on staged bridges, compatibility bindings, or incomplete facade enforcement.
- `legacy_compat`: flow exists mainly to preserve current behavior.
- `unsafe_to_freeze`: flow should not be frozen before more regression coverage or boundary isolation exists.

## Flow Audit Matrix

| Flow | Current entrypoint | Owning layer | Dependent modules | Current tests covering it | Evidence | Freeze status |
| --- | --- | --- | --- | --- | --- | --- |
| Repair flow | `core.runtime.governed_repair_api.execute_governed_repair_mutation`; repair transaction/review builders under `core/tasks/`; scheduler v734 repair bridge | `repair_runtime` with scheduler coordination | `core/tasks/runtime_repair_transaction.py`, `runtime_repair_transaction_review.py`, `runtime_repair_apply_transaction.py`, `runtime_repair_controlled_apply.py`, `core/runtime/repair_transaction_execution_bridge.py`, `core/runtime/repair_step_injector.py`, `core/tasks/scheduler_core/repair_injection_execution.py`, `repair_replay_continuation.py` | `tests/test_repair_chain_runtime.py`; boundary import and authority tests; repair transaction/apply suites exist outside the required smoke pack | Phase 4-D.4 smoke passed `tests/test_repair_chain_runtime.py` with 62 passing tests; boundary tests passed | `still_transitional` plus selected `stable_contract_candidate` wrappers |
| Rollback flow | `core.runtime.code_chain_patch_restore.request_code_chain_patch_restore`; mutation/repair rollback helpers under runtime/tasks | `mutation_runtime` and `repair_runtime`; Code Chain patch restore now runtime-owned | `core/runtime/code_chain_patch_restore.py`, `core/runtime/repair_rollback.py`, `core/tasks/runtime_repair_transaction.py`, mutation pipeline rollback components | `tests/test_runtime_mutation_authority_boundaries.py`; `tests/test_runtime_boundary_imports.py`; rollback behavior is indirectly exercised by repair chain tests | Phase 4-D.3 isolated agent rollback authority and Phase 4-D.4 boundary tests passed | `internal_only` with one `stable_contract_candidate` request wrapper |
| Governed mutation flow | `core.runtime.mutation_gateway.run_governed_mutation` | `mutation_runtime` | `core/runtime/mutation_gateway.py`, `mutation_runtime_pipeline.py`, `mutation_session.py`, `mutation_sandbox.py`, `mutation_patch_apply.py`, `mutation_approval.py`, `mutation_verification.py`, `mutation_boundary.py` | `tests/test_repair_chain_runtime.py`; controlled mutation contract tests exist in the suite; boundary import and authority tests | Phase 4-D.4 repair chain smoke passed; authority radar prevents external direct imports/calls into mutation internals | `stable_contract_candidate` for gateway; internals remain `internal_only` |
| Recovery flow | future recovery wrapper; current internal `runtime_recovery*` modules | `recovery_runtime` | `core/runtime/runtime_recovery_coordinator.py`, `runtime_recovery_policy.py`, `runtime_recovery_commit_gate.py`, recovery approval/dry-run/execution/evidence modules | Boundary import and authority tests guard external access; recovery-specific tests exist but are not part of the required smoke pack | Boundary tests passed in Phase 4-D.4; no dedicated recovery smoke in this phase | `still_transitional` / `internal_only` |
| Replay flow | read-only replay builders such as `build_runtime_replay_snapshot`; event replay; scheduler replay continuation helpers remain internal | Read-only reporting owned by runtime/tasks; retry/repair replay coordination owned by scheduler internal | `core/tasks/runtime_replay_snapshot.py`, `runtime_replay_narrative.py`, `core/runtime/event_replay.py`, `core/tasks/scheduler_core/repair_replay_continuation.py`, `retrying_repair_replay_state.py` | `tests/test_repair_chain_runtime.py`; runtime replay/audit tests exist elsewhere; boundary tests prevent external scheduler_core access | Phase 4-D.4 repair chain smoke passed; contract marks replay execution/mutation paths as internal | Read-only replay is `stable_contract_candidate`; scheduler replay continuation remains `internal_only` |
| Execution evidence flow | boot-created evidence seal/adapters; scheduler/task runtime/step executor evidence adapters | `system_boot` for wiring; scheduler/task runtime/step executor own event timing | `core/runtime/runtime_mainline_evidence_seal.py`, `scheduler_evidence_adapter.py`, `task_runtime_evidence_adapter.py`, `step_executor_evidence_adapter.py`, `runtime_evidence_persistence.py`, `runtime_evidence_registry.py`, `trace_runtime.py`, event modules | `tests/test_repair_chain_runtime.py`; runtime evidence tests exist elsewhere; boundary tests prevent external evidence authority leakage | Phase 4-D.4 repair chain smoke passed; no failure evidence in boundary tests | Read/query surface is `stable_contract_candidate`; adapter writes remain `internal_only` |
| Scheduler facade flow | `services.system_boot.ZeroSystem.tick`, `run_until_idle`, `health`, queue accessors; scheduler public lifecycle methods | `scheduler_facade` over `scheduler_internal`; actual enqueue remains scheduler-owned | `services/system_boot.py`, `core/tasks/scheduler.py`, `core/tasks/scheduler_core/*`, `TaskRepository`, `TaskRuntime`, `TaskRunner` | `tests/test_runtime_boundary_imports.py`, `tests/test_runtime_mutation_authority_boundaries.py`, `tests/test_scheduler_parser_helpers.py`; scheduler smoke exists outside this required pack | Phase 4-D.4 boundary tests passed; parser helper smoke passed with 18 tests | `stable_contract_candidate` for facade methods; private scheduler internals remain `internal_only` / `legacy_compat` |
| Agent loop runtime request flow | `core.agent.agent_loop.AgentLoop.run`; task-mode calls into scheduler; Code Chain restore request wrapper | `agent_loop` as request-only facade; runtime/tasks own mutation execution | `core/agent/agent_loop.py`, route policy, loop decision, component invoker, `core/runtime/code_chain_patch_restore.py`, scheduler public lifecycle | `tests/test_runtime_mutation_authority_boundaries.py`; `tests/test_runtime_boundary_imports.py`; agent loop smoke tests exist outside this required pack | Phase 4-D.3 removed direct rollback authority; Phase 4-D.4 boundary tests passed | `stable_contract_candidate` for request semantics; direct mutation remains forbidden |

## Per-Flow Notes

### 1. Repair Flow

- Current entrypoint: governed repair should enter through `execute_governed_repair_mutation` or review/proposal builders, not through repair transaction internals.
- Owning layer: `repair_runtime`, with scheduler-owned injection and replay continuation coordination.
- Remaining risks: scheduler v734 compatibility bridge still coordinates important repair injection/replay behavior; repair transaction lifecycle internals remain importable; review/approval wrappers are not yet consolidated into a public facade.
- Must not change before freeze: repair transaction state transitions, review approval/rejection semantics, injected-step idempotency, replay continuation metadata, scheduler-owned enqueue-after-injection behavior.
- Enforce later: import boundaries for repair transaction lifecycle internals, facade wrapper for `runtime.repairs.*`, evidence requirements for every repair proposal/review/commit/apply event.

### 2. Rollback Flow

- Current entrypoint: Code Chain patch restore now goes through `request_code_chain_patch_restore`; broader rollback remains inside mutation/repair/recovery internals.
- Owning layer: runtime-owned rollback helpers; agent layer may request restore but must not execute rollback directly.
- Remaining risks: rollback behavior is indirectly covered by repair chain tests; not all rollback helpers have explicit facade-level contract tests.
- Must not change before freeze: return payload keys, reason strings, backup-missing behavior, target write behavior, and failure normalization for Code Chain restore.
- Enforce later: require rollback authority annotations and regression tests for mutation rollback, repair rollback, and recovery rollback separately.

### 3. Governed Mutation Flow

- Current entrypoint: `run_governed_mutation`.
- Owning layer: `mutation_runtime`.
- Remaining risks: mutation pipeline internals remain broad and importable; datetime warnings in `mutation_boundary.py` are noisy but not a freeze blocker for behavior.
- Must not change before freeze: gateway request normalization, approval handling, sandbox/patch sequencing, rollback capture, verification status, evidence output, and failure packaging.
- Enforce later: public facade wrapper, import guard for mutation internals, mandatory evidence schema assertions, permission checks by caller layer.

### 4. Recovery Flow

- Current entrypoint: no public recovery entrypoint should be frozen yet; current recovery execution is internal.
- Owning layer: `recovery_runtime`.
- Remaining risks: recovery is high-authority and has no required Phase 4-E smoke target; public wrapper shape and approval semantics are not frozen.
- Must not change before freeze: recovery policy decisions, dry-run behavior, commit gate semantics, rollback hooks, audit evidence production.
- Enforce later: dedicated recovery smoke pack, import boundary tests for all `runtime_recovery*` execution internals, recovery-specific approval and audit evidence requirements.

### 5. Replay Flow

- Current entrypoint: read-only replay through snapshot/narrative/event replay builders; retry/repair replay continuation remains scheduler internal.
- Owning layer: read-only replay belongs to runtime/tasks reporting; mutating replay continuation belongs to scheduler internal.
- Remaining risks: retry repair replay state and continuation are internal helpers and should not be exposed; replay must remain readonly outside scheduler-owned retry paths.
- Must not change before freeze: deterministic replay snapshot shape, readonly behavior, continuation metadata, idempotent retry/repair replay decisions.
- Enforce later: tests that external layers cannot call replay continuation helpers, explicit read-only replay facade, replay determinism assertions.

### 6. Execution Evidence Flow

- Current entrypoint: boot-created evidence seal and adapters; read-only status/timeline/audit builders.
- Owning layer: system boot wires evidence; scheduler, TaskRuntime, and StepExecutor own event timing for their domains.
- Remaining risks: evidence write adapters remain internal and could falsify provenance if exposed; facade read/write split is not implemented.
- Must not change before freeze: event ordering, evidence IDs/refs, adapter ownership, trace persistence, audit artifact shape.
- Enforce later: evidence service wrapper, import guards for emitters/adapters, schema validation tests, monotonic provenance checks.

### 7. Scheduler Facade Flow

- Current entrypoint: `ZeroSystem` facade and scheduler public lifecycle methods.
- Owning layer: scheduler facade for external access; scheduler internal for tick, queue, dispatch, finalize, enqueue primitive, compatibility bindings, and evidence timing.
- Remaining risks: `services/system_boot.py` still directly imports `Scheduler` as a bootstrap exception; scheduler public/private boundary is documented but not fully hidden behind `zero.runtime`.
- Must not change before freeze: actual enqueue primitive execution, queue transition semantics, tick/run-until-idle behavior, worker release routing, scheduler compatibility binding order.
- Enforce later: introduce facade module, shrink external imports to facade only, add tests for private scheduler import bans outside bootstrap/tests/runtime/tasks.

### 8. Agent Loop Runtime Request Flow

- Current entrypoint: `AgentLoop.run` and task-mode scheduler requests.
- Owning layer: agent loop is request-only; scheduler/runtime layers own mutation execution.
- Remaining risks: agent loop still contains broad self-edit/request routing and legacy compatibility paths; not all agent smoke tests are part of the required Phase 4-E pack.
- Must not change before freeze: request-only semantics, task submission behavior, Code Chain restore payload compatibility, route policy classification, scheduler-backed task flow.
- Enforce later: add focused agent-loop boundary tests, require all self-edit mutation to use governed mutation/repair wrappers, prevent direct StepExecutor/TaskRuntime/scheduler private access from agent code.

## Freeze Recommendations

Freeze first as contract candidates:

- `runtime.mutations.run_governed(request)` gateway behavior.
- Read-only status, timeline, replay, audit, event, and evidence query builders.
- `ZeroSystem` health/tick/run-until-idle/queue read facade behavior.
- Agent loop request-only boundary after Code Chain restore isolation.
- Boundary import and mutation authority tests as architecture radar.

Keep internal before public freeze:

- scheduler private methods and `scheduler_core` helpers;
- repair injection execution and replay continuation helpers;
- mutation pipeline internals;
- repair transaction/apply/control internals;
- recovery execution internals;
- evidence emitters/adapters;
- queue/dispatcher/worker primitives;
- compatibility `_zero_*` bindings.

Do not freeze yet:

- public recovery API shape;
- public rollback API shape beyond the narrow Code Chain restore request helper;
- direct guarded step execution as an external API;
- scheduler as a direct external API surface;
- legacy controlled mutation pathways.

## Phase 4-E Completion Criteria

This audit is complete when:

- the eight requested runtime flows are classified;
- each flow lists entrypoint, owning layer, dependent modules, tests, evidence, risks, freeze blockers, and future enforcement;
- only `docs/runtime_mainline_freeze_audit.md` is created or updated for the audit itself;
- boundary import, mutation authority, repair chain runtime, and scheduler parser helper smoke targets are run afterward;
- no runtime behavior, scheduler code, production code, file layout, or warnings are changed.
