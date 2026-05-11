# ZERO Scheduler Responsibility Audit v1

Date: 2026-05-11

Scope: `core/tasks/scheduler.py`

This audit maps current scheduler responsibilities and recommends extraction order. It is intentionally read-only: no runtime behavior, scheduler flow, planner behavior, guard behavior, UI, GitHub, or tests are changed by this document.

## Executive Summary

`Scheduler` is currently both an orchestration boundary and a compatibility bridge. The stable core responsibilities are queue lifecycle, dispatch coordination, task state handoff, and persistence synchronization. The unstable or extraction-ready responsibilities are display formatting, repair step synthesis, retrying repair bridges, queue hygiene policies, and legacy compatibility wrappers.

The next phase should avoid a broad scheduler split. The safest path is to peel off small, side-effect-bounded helpers while preserving public method contracts and existing monkey-patch order.

## Current Responsibility Map

| Category | Current scheduler responsibility | Keep in scheduler? | Suggested owner |
| --- | --- | --- | --- |
| queue lifecycle | Rebuild ready queue, apply runtime dispatch gate, dispatch until worker capacity, cancel stale queue rows, run queue hygiene at tick/snapshot boundaries. | Partly | Scheduler owns orchestration; hygiene policy can move to queue policy/helper. |
| task state transition | Hydrate task, skip terminal tasks, sync runner result, requeue retry/queued tasks, collapse runtime state back to repo. | Partly | Scheduler keeps transition orchestration; state mutation rules should live in runtime/state helpers. |
| planning handoff | Choose agent loop/planner gateway/replanner fallback, evaluate replan eligibility, record replan trace, optionally apply replans. | Partly | Scheduler keeps handoff; replan decision policy should move to planner/replan service. |
| execution dispatch | Tick loop, dispatcher integration, worker slot dispatch, build tick results. | Yes | Scheduler remains owner. |
| step execution bridge | Construct `StepExecutor`, pass simple task ticks to helper/runner, route Code Chain workflow steps to `TaskRunner`. | Partly | Scheduler keeps dependency wiring; execution semantics belong to TaskRunner/StepExecutor. |
| repair / patch orchestration | Detect repairable failures, expire repair tasks, manage repair fingerprints, inject retrying compile repair steps, attach repair-chain summary. | Mostly no | Repair queue policy, repair bridge, and repair summary should be separate services. |
| verification / rollback | Mostly indirect: compact rollback fields for CLI, attach orchestration summary, route verify workflow steps. Does not own apply_patch verification engine. | No for engine, yes for status display | StepExecutor/TaskRunner own verify/rollback; Scheduler may summarize only. |
| guard / policy | Instantiate `ExecutionGuard`, apply runtime dispatch gate from persisted blockers/review state, validate repair task scope in queue hygiene. | Partly | Guard/policy decisions should remain outside scheduler; scheduler may enforce dispatch-level wait. |
| trace / audit | Promote execution traces, save/load task traces through helper methods, maintain replan trace, write loop fallback trace. | Partly | Trace persistence/helpers should own format; scheduler may attach tick-level aggregate. |
| repo/runtime persistence | Create default TaskRepository, persist task payload, sync runtime state, read/write runtime state in compatibility repair bridge. | Partly | Repository/runtime persistence helpers should own IO details. |
| display / formatting | Compact runner results for CLI/manual smoke output and format replan suggestions. | No | CLI/display adapter. |
| CLI compatibility | `run_next`, `run_once`, compact results, broad fallback behavior, legacy public method names. | Yes, temporarily | Scheduler keeps public API until compatibility layer exists. |
| legacy compatibility | Versioned wrappers from v7.x/v3.x monkey-patch methods, repair allowlists, workflow advancement fixes, retrying bridge. | Temporarily | Freeze until covered; extract one wrapper family at a time. |

## Responsibilities To Keep In Scheduler

1. Tick orchestration:
   - Increment/track current tick.
   - Rebuild queue before dispatch.
   - Apply dispatch gate for blocked/review/waiting runtime states.
   - Dispatch ready tasks through `TaskDispatcher`.
   - Return tick summary.

2. Dependency wiring:
   - Construct or accept injected `StepExecutor`, `ExecutionGuard`, `TaskDispatcher`, `WorkerPool`, `Replanner`, `TraceRuntime`, and `RepairChainReader`.
   - Preserve constructor compatibility for existing callers.

3. Public compatibility surface:
   - `run_next`, `run_once`, `run_one`, `run_one_step`.
   - Queue snapshot/rows methods while CLI and manual harnesses depend on them.

4. Handoff coordination:
   - Decide whether to use agent loop, TaskRunner, simple runner, or fallback path.
   - Do not implement step semantics directly beyond compatibility shims.

5. Dispatch-level safety gate:
   - It is appropriate for scheduler to prevent dispatch of tasks whose persisted runtime state says wait, blocked, or review required.
   - It should not become a verify engine or patch policy engine.

## Responsibilities To Move Out

1. Repair task hygiene policy:
   - Expiring stale repair tasks.
   - Duplicate repair task detection.
   - Fingerprint pending-lock lifecycle.
   - Invalid repair task scope failure.
   - Suggested target: `core/tasks/scheduler_core/repair_queue_hygiene.py` or a repair orchestration module.

2. Retrying repair bridge:
   - `_zero_v734_*` compile-target extraction.
   - Deterministic source synthesis.
   - Repair step injection.
   - Runtime state read/write used only for repair bridge.
   - Suggested target: `core/runtime/repair_bridge.py` or `core/tasks/repair_step_injector.py`.

3. Replan policy:
   - Repairable failure classification.
   - Replan budget/fingerprint checks.
   - Replan trace event construction.
   - Suggested target: `core/planning/replan_policy.py`.

4. Display formatting:
   - `_compact_runner_result`.
   - CLI-friendly multi-edit summaries.
   - Suggested target: CLI/result presenter module.

5. Trace persistence details:
   - Loop fallback trace file writes.
   - Trace save/load/promote wrappers that only pass through helper behavior.
   - Suggested target: trace helper modules, keeping scheduler as caller only.

6. Runtime state IO inside scheduler:
   - Direct `runtime_state.json` read/write in repair compatibility bridge.
   - Suggested target: TaskRuntime or runtime-state helper.

## Blocks That Should Not Move Yet

1. Public constructor and public method compatibility.
   - Many tests and CLI flows likely instantiate Scheduler with broad optional dependencies.
   - Moving this before a facade exists would be high risk.

2. `tick()` orchestration.
   - It is the central stable boundary for queue rebuild, gate, dispatch, and result aggregation.
   - Extract helpers around it before changing the method itself.

3. `run_one_step()` compatibility wrapper chain.
   - Multiple late wrappers attach orchestration summary, compact results, and retry bridge behavior.
   - The ordering is behaviorally significant.

4. Code Chain workflow advancement wrapper.
   - It protects analyze -> repair -> verify progression by routing those steps through TaskRunner.
   - Moving it without equivalence tests risks reintroducing stale replan metadata failures.

5. Runtime dispatch gate.
   - It protects blocker/review state from being bypassed by queue dispatch.
   - It can be extracted later, but should remain behavior-identical and scheduler-invoked.

## Good Candidates For Next Extraction

1. Result compaction.
   - Low behavioral risk.
   - Pure formatting.
   - Easy to preserve with snapshot/manual tests.

2. Repair chain summary attachment.
   - Mostly read-only.
   - Already delegates deep parsing to `RepairChainReader`.
   - Can become a small result-enrichment helper.

3. Queue hygiene/fingerprint cleanup.
   - Medium risk but well-bounded.
   - Has clear inputs/outputs and policy comments.
   - Should move after adding focused regression tests for stale, duplicate, invalid, and terminal queue rows.

4. Replan classification helpers.
   - Medium risk.
   - Mostly pure decision logic, but tied to legacy allowlists.
   - Extract only after locking current repairable-step matrix.

5. Retrying compile repair bridge.
   - Higher risk because it mutates task steps and runtime state.
   - Extract after queue hygiene and replan policy are stable.

## Risk Ranking

| Rank | Area | Risk | Reason |
| --- | --- | --- | --- |
| 1 | `run_one_step()` wrapper chain | High | Late monkey-patches compose behavior; ordering changes can alter runtime outcomes. |
| 2 | retrying repair bridge | High | Mutates steps, runtime state, repo payload, and queue readiness. |
| 3 | Code Chain workflow advancement | High | Prevents stale simple-runner/replan behavior from breaking analyze/repair/verify progression. |
| 4 | queue hygiene/fingerprint lifecycle | Medium-high | Can fail or unblock tasks incorrectly if task status or age policy changes. |
| 5 | runtime dispatch gate | Medium-high | Safety boundary for blocked/review tasks; must fail closed. |
| 6 | replan policy | Medium | Decision-only in many paths, but affects whether repair is attempted. |
| 7 | trace/audit attachment | Medium-low | Mostly metadata, but consumers may rely on fields. |
| 8 | result compaction/display | Low | Presentation-only if full runner result is synced first. |
| 9 | constructor dependency wiring | Low-medium | Simple but broad caller compatibility surface. |

## Recommended Extraction Order

1. Add tests before moving behavior.
   - Lock queue lifecycle, dispatch gate, retrying repair bridge, Code Chain workflow advancement, and compact result shape.

2. Extract display/result compaction.
   - Move `_compact_runner_result` to a presenter/helper.
   - Keep Scheduler calling it from the same points.

3. Extract repair-chain summary attachment.
   - Move `_read_repair_chain_orchestration_summary` and `_attach_orchestration_summary_to_runner_result` into a read-only enrichment helper.
   - Keep exact field names: `orchestration_summary.repair_chain` and `repair_chain_orchestration`.

4. Extract queue hygiene and fingerprint lifecycle.
   - Move v7.2.4/v7.2.6 cleanup policy as a unit.
   - Keep Scheduler-owned timing: call at tick/snapshot boundaries.

5. Extract replan policy helpers.
   - Move repairable failure classification, replan budgets, step fingerprints, and trace event construction.
   - Keep Scheduler responsible for invoking replanner and applying accepted plans.

6. Extract retrying repair bridge.
   - Move compile-target detection, deterministic fix synthesis, and repair step injection together.
   - Keep Scheduler responsible only for detecting `retrying` status and calling the bridge.

7. Revisit `run_one_step()` wrapper chain.
   - Only after the above pieces have tests and stable helper contracts.
   - Prefer a facade that preserves public behavior over a broad rewrite.

## Category Notes

### queue lifecycle

Scheduler should own queue orchestration, not all queue policy. Rebuild, gate, dispatch, and tick summary belong here. Stale repair cleanup, fingerprint cleanup, and duplicate repair expiration are policy-heavy and should move behind a helper while remaining invoked by scheduler.

### task state transition

Scheduler is currently a bridge between repo task payloads and runtime state. It should keep high-level transition coordination, but step index mutation, runtime-state JSON IO, and repair-state mutation should move toward TaskRuntime or focused state helpers.

### planning handoff

Scheduler should choose when to hand off to planner/replanner/agent loop. It should not grow more plan-quality policy. Replan eligibility and fingerprint rejection are extraction candidates once covered.

### execution dispatch

This is the scheduler's core durable responsibility. `tick()`, ready queue rebuild, dispatch gate, dispatcher invocation, and tick result aggregation should remain.

### step execution bridge

Scheduler may wire and route to `StepExecutor` and `TaskRunner`, but `StepExecutor` owns step handlers and apply_patch verification/transaction behavior. Scheduler should not interpret patch transactions beyond metadata summaries.

### repair / patch orchestration

Scheduler currently contains compatibility repair orchestration. Keep it frozen short-term. Next extraction should isolate repair queue hygiene first, then retrying repair bridge. Do not move apply_patch transaction/verify/rollback into scheduler.

### verification / rollback

Scheduler should only surface verification/rollback metadata. Verification engines, rollback execution, and transaction status transitions belong to StepExecutor/TaskRunner/runtime layers.

### guard / policy

Scheduler can enforce dispatch-level wait states. Path/command/patch policy remains in `ExecutionGuard` and repo sandbox policy. Guard should remain gate/metadata only.

### trace / audit

Scheduler can aggregate tick-level execution trace. Trace serialization, trace formatting, and fallback trace logs should be helper-owned.

### repo/runtime persistence

Scheduler should not be the long-term owner of raw runtime-state file IO. It may coordinate sync, but persistence details should stay in repository/runtime helpers.

### display / formatting

Display compaction is low-risk to extract. It should be kept separate from state sync so compact output never becomes the only stored result.

### CLI compatibility

CLI compatibility is a valid scheduler responsibility for now. Public methods and compact outputs should be preserved until a dedicated CLI facade exists.

### legacy compatibility

The versioned patch blocks should be treated as frozen behavior capsules. Move only one capsule at a time, after tests prove identical input/output behavior.

## Boundary Statement

Scheduler should remain the coordinator of when a task is eligible to run and which runtime component receives it. It should not become the owner of step semantics, patch verification, rollback execution, command/path policy, or display presentation beyond temporary compatibility shims.
