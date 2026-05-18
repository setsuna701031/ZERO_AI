# Scheduler Ownership Collapse Audit - Phase 3-I

Date: 2026-05-18

Scope: `core/tasks/scheduler.py` after the Phase 3-G and Phase 3-H repair replay extractions.

This is a read-only audit. It does not change runtime behavior, scheduler code, runtime modules, or tests.

## Executive Summary

`scheduler.py` is now closer to an orchestration boundary, but it still contains several behavior-bearing ownership clusters:

- true scheduler core: queue eligibility, dispatch orchestration, worker coordination, and public task lifecycle methods;
- persistence coordination: repository payload writes, task snapshots, best-effort runtime-state synchronization, and trace persistence calls;
- runtime evidence ownership: enqueue/dequeue/cancel/worker evidence emission through the scheduler evidence adapter;
- compatibility shims: versioned v7.x/v3.x monkey-patch capsules that preserve legacy behavior and ordering;
- repair queue policy: v7.2.4 repair task hygiene plus v7.2.6 pending repair lock lifecycle;
- repair replay bridge residue: compile-target discovery and narrow deterministic repair-step synthesis remain in scheduler, while replay decision, injection execution, and continuation packaging have moved to helpers.

The safest next collapse is not a broad rewrite. Future extraction should move one capsule at a time while `scheduler.py` keeps the public method bindings and actual enqueue primitive.

## Remaining Ownership Responsibilities

| Area | Current scheduler responsibility | Category | Recommendation |
| --- | --- | --- | --- |
| Queue lifecycle | Ready queue rebuild, queue transition decisions, dependency checks, enqueue/remove/block/unblock calls, queue snapshot/rows public API. | True ownership boundary | Keep core orchestration in scheduler. Extract only policy/formatting helpers. |
| Actual enqueue primitive | `_enqueue_repo_task_if_ready(...)` hydrates tasks, evaluates queue transition, mutates queue, releases workers on terminal removal, emits evidence. | Must-remain runtime core for now | Keep in scheduler until a queue runtime facade owns evidence and worker release semantics. |
| Dispatch/finalize routing | Tick flow, dispatcher handoff, worker pool coordination, dispatch result handling/finalization. | Must-remain runtime core | Do not move during repair extraction work. |
| Task public lifecycle | `create_task`, `submit_task`, `submit_existing_task`, pause/resume/cancel/priority/status methods. | True ownership boundary plus compatibility surface | Keep public methods. Extract internal policy only after facade tests. |
| Repository persistence | `_persist_task_payload(...)`, task snapshot saves, fallback repository method handling. | True ownership boundary, but IO details are extractable | Keep call sites. Low-medium risk to extract the writer adapter after persistence contract tests. |
| Runtime-state persistence | `_write_runtime_state_file_safe(...)`, `_persist_code_chain_runtime_state_if_available(...)`, v7.3.4 runtime-state read/write for retry bridge. | Compatibility/runtime persistence bridge | High risk unless covered by replay, retry, code-chain, and runtime-state round-trip tests. |
| Runtime evidence | `_emit_scheduler_evidence(...)` and enqueue/dequeue/cancel/worker evidence call sites. | True ownership boundary | Keep scheduler as event source. A future evidence helper can format/route events only. |
| v7.2.4 hygiene lifecycle | Repair task expiration, invalid repair scope failure, stale fingerprint cleanup, queue row cancellation during tick/snapshot/rows. | Compatibility shim plus policy | High-risk extraction requiring a dedicated hygiene regression net. |
| v7.2.6 pending repair lifecycle | Pending fingerprint reservation release, stale pending lock retry, create_task wrapper, duplicate lookup wrapper. | Compatibility shim plus policy | High-risk extraction requiring replay and concurrency-adjacent tests. |
| v7.3.3 replay bridge | Code Chain workflow tick advancement routes analyze/repair/verify through TaskRunner. | Compatibility shim / monkey patch binding | Must remain frozen until bridge-specific replay tests cover ordering and task-runner fallback. |
| v7.3.4 retry bridge | Detect retrying status, forward replay decision, call repair injection transaction helper, enqueue continuation, preserve monkey-patch bindings. | Compatibility shim | Scheduler should keep binding and enqueue primitive; remaining compile repair synthesis is a future extraction target. |
| Review bindings | approve/reject/get review queue monkey patch methods and runtime repair transaction review forwarding. | Compatibility shim | Keep bindings; review payload formatting could move later with approval tests. |
| Result compaction and summary enrichment | Compact runner result, attach repair-chain orchestration summary, final run_one_step wrapper. | Safe future extraction target | Low-medium risk if result-shape snapshots are added. |

## Classification

### True Ownership Boundaries

- `tick()` orchestration and scheduler round limits.
- Queue rebuild, queue transition invocation, and queue mutation through `scheduler_queue`.
- Dispatch handoff to `TaskDispatcher` and worker pool coordination.
- Public task lifecycle methods and constructor dependency wiring.
- Scheduler evidence emission as the source of queue and worker lifecycle events.
- Repository task persistence coordination, because scheduler is the public task lifecycle owner.

### Compatibility Shims

- v7.0.2 repair step preservation.
- v7.0.3 and v7.3.1 repairable-step allowlist widening.
- v7.2.4 queue hygiene patch chain.
- v7.2.6 pending repair enqueue lock lifecycle.
- v7.3.3 Code Chain workflow tick advancement bridge.
- v7.3.4 retrying repair bridge.
- v3.5.2 final `run_one_step` result enrichment.
- Review queue approve/reject/get bindings.

### Monkey Patch Bindings

These assignments are behavior-bearing because ordering changes affect the final method graph:

- `Scheduler._plan_goal = _zero_v702_scheduler_plan_goal`
- `Scheduler._execute_simple_step = _zero_v702_scheduler_execute_simple_step`
- `Scheduler._is_repairable_failure = ...` and `Scheduler._normalize_replan_metadata = ...`
- `Scheduler.cleanup_task_queue_hygiene = ...`
- `Scheduler.tick = ...`
- `Scheduler.get_queue_snapshot = ...`
- `Scheduler.get_queue_rows = ...`
- `Scheduler.create_task = ...`
- `Scheduler._find_active_duplicate_repair_task = ...`
- `Scheduler._run_simple_task_tick = ...`
- `Scheduler.run_one_step = ...`
- `Scheduler._sync_runner_result_and_requeue_if_ready = ...`
- review queue method bindings.

Keep these bindings in `scheduler.py` until there is a deliberate compatibility registry or facade that preserves ordering explicitly.

### Safe Future Extraction Targets

Low-risk targets:

- result compaction and display-only payload shaping;
- repair-chain summary attachment, as long as `RepairChainReader` remains the parser;
- queue row/snapshot formatting, already mostly helper-owned;
- pure path parsing, command planning, trace serialization wrappers, and public task record formatting, already partly extracted;
- evidence payload formatting, if scheduler remains the event source and emitter call sites do not move.

Medium-risk targets:

- `_persist_task_payload(...)` into a repository persistence adapter;
- `_write_runtime_state_file_safe(...)` into a runtime-state persistence helper;
- `submit_existing_task` blocked/queued result packaging;
- review queue result packaging.

High-risk targets:

- v7.2.4 repair hygiene lifecycle;
- v7.2.6 pending repair lock lifecycle;
- `_enqueue_repo_task_if_ready(...)`;
- v7.3.3 workflow tick bridge;
- v7.3.4 compile repair synthesis and runtime-state read/write;
- `run_one_step` monkey-patch chain;
- worker release routing and dispatch/finalize flow.

### Must-Remain Runtime Core

- actual enqueue primitive execution;
- worker release routing;
- dispatch/finalize routing;
- blocked/unblocked transition routing at dispatch and enqueue boundaries;
- tick orchestration;
- scheduler evidence emission;
- public method compatibility until a facade exists.

## Remaining Replay And Runtime Mutation Paths

Replay/runtime mutation still present in `scheduler.py`:

- v7.3.4 retry bridge detects `retrying`/`retry` in `_zero_v734_run_one_step(...)` and forwards to `_zero_v734_land_repair_steps(...)`;
- v7.3.4 still owns compile-target resolution and deterministic Python source repair synthesis before delegating injection execution;
- v7.3.4 reads and writes `runtime_state.json` through `_zero_v734_read_runtime_state(...)` and `_zero_v734_write_runtime_state(...)`;
- `_zero_v734_sync_runner_result_and_requeue_if_ready(...)` can enqueue refreshed retrying tasks after the original runner-result sync;
- `_collapse_non_retryable_retrying_task(...)` mutates retrying tasks to failed, writes task payload, writes runtime state, cancels queue, and releases worker;
- `_persist_code_chain_runtime_state_if_available(...)` writes Code Chain output into TaskRuntime when available;
- `_force_repo_task_state(...)` can force persisted task status and route blocked/queued/finished/failed transitions;
- `_write_runtime_state_file_safe(...)` writes a task-shaped runtime-state file for failure collapse compatibility.

Replay/runtime mutation no longer owned by scheduler after Phase 3-G/H:

- replay decision state preparation is helper-owned;
- repair injection transaction mutation is helper-owned;
- post-injection continuation packaging and enqueue intent are helper-owned.

Scheduler still owns the call boundary and actual enqueue primitive.

## Remaining Enqueue Ownership

Scheduler enqueue ownership remains in these forms:

- `_enqueue_repo_task_if_ready(...)` is the central enqueue primitive and should remain scheduler-owned for now;
- `route_enqueue_repo_task_if_ready(...)` is called from submit/resume/sync paths as a router helper, but scheduler still supplies the runtime context;
- v7.3.4 continuation uses helper-produced enqueue decisions, then scheduler calls `_enqueue_repo_task_if_ready(...)`;
- v7.2.4/v7.2.6 wrappers call hygiene before tick/snapshot/create to keep queue/fingerprint state coherent;
- enqueue evidence is emitted by scheduler after queue mutation succeeds.

Extraction guidance:

- Do not move `_enqueue_repo_task_if_ready(...)` without new tests for terminal removal, blocked route, unblocked route, duplicate queue entries, overwrite behavior, worker release, and evidence emission.
- It is safe to extract enqueue decision packaging only when actual queue mutation stays in scheduler.

## Remaining Runtime Persistence Ownership

Scheduler still coordinates three persistence layers:

- repository task payloads through `_persist_task_payload(...)`;
- task snapshot files through `_save_task_snapshot_safe(...)`;
- runtime-state compatibility writes through `_write_runtime_state_file_safe(...)`, `_persist_code_chain_runtime_state_if_available(...)`, and v7.3.4 runtime-state helpers.

Ownership split:

- Scheduler should remain the caller that decides when task lifecycle state must be persisted.
- Repository adapter or task persistence helper can own the `replace_task`/`upsert_task`/`create_task` fallback ladder.
- Runtime modules should eventually own runtime-state file format and write semantics.

High-risk persistence moves:

- moving v7.3.4 runtime-state read/write before replay idempotency tests;
- moving `_write_runtime_state_file_safe(...)` before retry collapse tests;
- moving Code Chain runtime persistence before Code Chain smoke/regression tests.

## Runtime Evidence Ownership

Scheduler evidence ownership remains appropriate:

- queue events originate at scheduler queue mutation points;
- cancel events originate in scheduler public lifecycle methods;
- worker release and dispatch lifecycle are coordinated by scheduler/dispatcher;
- evidence adapter is optional and fail-soft, preserving minimal runtime compatibility.

Future extraction should only move event construction/routing into a helper. The event source and timing should remain scheduler-owned unless a full runtime event bus replaces it.

## v7.2.4 Hygiene Lifecycle Audit

Current responsibilities:

- calls original hygiene first;
- expires stale queued/created repair tasks;
- expires stale legacy self-edit tasks;
- validates repair task scope and fails invalid repair tasks closed;
- de-duplicates repair tasks by fingerprint;
- cancels queue rows for missing or terminal tasks;
- cleans stale fingerprint records and pending reservations;
- patches `tick`, `get_queue_snapshot`, and `get_queue_rows`.

Risk:

- High. It combines queue hygiene, repair policy, fingerprint IO, task failure mutation, and public queue reporting.

Required regression net before extraction:

- stale queued repair task expiration;
- invalid repair scope failure;
- duplicate active repair suppression;
- terminal task queue-row cancellation;
- missing task queue-row cancellation;
- stale fingerprint index removal;
- snapshot/rows still include `queue_hygiene`;
- tick still runs hygiene before dispatch.

Recommended extraction:

- Extract as one policy capsule, not as individual helpers.
- Keep scheduler wrapper bindings and call timing in `scheduler.py`.
- Helper should return the same result fields, including v724-specific counts.

## v7.2.6 Pending Repair Lifecycle Audit

Current responsibilities:

- defines `__pending_repair_enqueue__` sentinel;
- releases stale pending fingerprint locks;
- wraps duplicate lookup to ignore stale pending locks;
- wraps cleanup with a shorter pending TTL;
- wraps `create_task` to retry once when a stale pending lock suppressed creation;
- releases pending reservation after failed creation or exceptions;
- patches `create_task`, `tick`, `_find_active_duplicate_repair_task`, and `cleanup_task_queue_hygiene`.

Risk:

- High. It is concurrency-adjacent even in a single-process CLI because interruption between reservation and task registration can block future repairs.

Required regression net before extraction:

- pending lock released after TTL;
- stale pending lock does not suppress a later valid repair;
- fresh pending lock still suppresses same in-flight duplicate;
- create failure releases pending lock;
- create exception releases pending lock and re-raises;
- retry-after-release creates exactly one task;
- tick cleanup uses one-second pending TTL.

Recommended extraction:

- Extract only after v724 extraction or together with it as a repair queue lifecycle capsule.
- Preserve the pending sentinel string and one-second grace behavior exactly.

## Low-Risk Future Extraction

- Result compaction/presentation helpers.
- Repair-chain summary attachment.
- Evidence event payload formatting.
- Repository persistence fallback ladder, after tests assert `replace_task`, `upsert_task`, `create_task`, and `add_task` fallback behavior.
- Review queue payload formatting.

## High-Risk Extraction Requiring New Regression Nets

- v724/v726 repair queue lifecycle.
- `_enqueue_repo_task_if_ready(...)` queue primitive.
- v733 workflow tick bridge.
- v734 compile repair synthesis and runtime-state compatibility IO.
- `run_one_step` wrapper chain and final v3.5.2 result enrichment.
- Runtime persistence writes during retry collapse and Code Chain forced edit flows.
- Any dispatch/finalize or worker release routing.

## Recommended Next Steps

1. Add no behavior changes until the current Phase 3-G/H extraction diff is stabilized.
2. Add a dedicated repair queue lifecycle regression suite for v724/v726.
3. Extract v724/v726 as a single repair queue lifecycle helper, keeping scheduler-owned call timing and monkey-patch bindings.
4. Add enqueue primitive regression tests before considering queue ownership collapse.
5. Keep runtime evidence emission timing in scheduler until a broader runtime event bus boundary exists.

## Runtime Ownership Seal Verification - Phase 3-K

Verification date: 2026-05-18

Sweep summary:

- No Phase 3 replay injection mutation logic has leaked back into `scheduler.py`.
- Replay decision/reasoning remains delegated to `core/tasks/scheduler_core/retrying_repair_replay_state.py`.
- Repair injection mutation execution remains delegated to `core/tasks/scheduler_core/repair_injection_execution.py`.
- Post-injection continuation packaging and enqueue intent remain delegated to `core/tasks/scheduler_core/repair_replay_continuation.py`.
- v733 Code Chain replay bridge logic remains isolated behind `core/tasks/scheduler_core/code_chain_tick_replay_bridge.py`, with `scheduler.py` retaining only the compatibility binding.
- `scheduler.py` still owns actual enqueue execution through `_enqueue_repo_task_if_ready(...)`.
- `scheduler.py` still owns runtime evidence timing through `_emit_scheduler_evidence(...)`.
- `scheduler.py` still owns compatibility monkey-patch bindings and runtime boundary calls.

Observed scheduler call sites:

- `prepare_retrying_repair_replay_state(...)` is imported and called from the v734 bridge only.
- `execute_repair_injection_transaction(...)` is imported and called from the v734 bridge only.
- `build_already_injected_replay_continuation(...)` and `build_injected_replay_continuation(...)` are imported and called from the v734 bridge only.
- v734 enqueue-after-continuation is limited to `_enqueue_repo_task_if_ready(...)` calls using helper-produced enqueue decisions.
- `repair_steps_injected` mutation markers are present in scheduler_core helpers, not in scheduler replay mutation code.

Residual non-Phase-3 mutation paths:

- `scheduler.py` still mutates `task["steps"]` in older replan and fallback-plan paths. These are not replay injection paths and are outside the Phase 3 replay extraction boundary.
- `scheduler.py` still performs runtime-state persistence writes for retry collapse, Code Chain compatibility, and v734 runtime-state bridge IO. These remain future persistence ownership migration targets.
- v724 queue hygiene and v726 pending repair lock lifecycle remain scheduler compatibility zones and were not changed by this verification.

Seal conclusion:

The Phase 3 replay ownership seal is intact. Scheduler retains ownership, enqueue primitive execution, compatibility bindings, and runtime evidence ownership. Replay reasoning, mutation execution, and continuation orchestration remain in scheduler_core helpers.

## Boundary Statement

After Phase 3-G/H, scheduler should be treated as the owner of orchestration timing, queue mutation, public task lifecycle, persistence coordination, and evidence timing. It should not regain ownership of repair injection mutation or replay continuation packaging. Future extraction should reduce policy and formatting in scheduler without moving actual enqueue execution, dispatch/finalize routing, worker release routing, or monkey-patch compatibility bindings prematurely.
