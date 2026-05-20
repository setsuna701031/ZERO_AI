# Scheduler Compatibility Surface Audit

Date: 2026-05-20

Post-L4 invariant: runtime owns execution authority; scheduler coordinates task lifecycle, queue state, dispatch timing, compatibility adapters, and scheduler evidence timing. Scheduler must not become the owner of command execution, governed runtime evidence, repair authority, recovery verification, or runtime governance decisions.

This audit is documentation-only. It does not split `scheduler.py`, refactor `system_boot.py`, move ownership, or change production behavior.

## Commands Used For Inspection

- `Get-Content -Path core/tasks/scheduler.py`
- `Get-ChildItem -Path core/tasks/scheduler_core -File`
- `Get-Content -Path tests/test_runtime_mainline_freeze_contract.py`
- `Get-Content -Path tests/test_runtime_topology_freeze_gate.py`
- `rg -n "subprocess\.|os\.system|Popen|check_output|check_call|safe_subprocess_run|Executor\(|core\.runtime\.executor|runtime_evidence|runtime_audit|governed_runtime|build_runtime_evidence_record|write_text|write_bytes|open\(|json\.dump|Path\(.*\)\.write|\.write_text|\.write_bytes" core/tasks/scheduler.py core/tasks/scheduler_core core/tasks/scheduler_execution_gateway.py core/tasks/execution_gateway_runtime.py core/tasks/execution_gateway.py`
- `rg -n "execute|run_one_step|run_task|repair|replay|enqueue|dequeue|dispatch|worker|runtime_state|atomic|write|apply|mutation|approval|review" core/tasks/scheduler.py core/tasks/scheduler_core -g "*.py"`
- `rg -n "class |def " core/tasks/scheduler_core -g "*.py"`

## Classification Table

| Surface | Current role | Classification | Notes |
| --- | --- | --- | --- |
| `Scheduler.tick`, `run_once`, `run_next`, `run_one` | Drives queue rebuild, dispatch gate, worker dispatch, result finalization | coordination/orchestration logic | Keep stable during post-L4 stabilization; future slimming can extract only after behavior is locked by tests. |
| `Scheduler.enqueue`, `dequeue`, queue snapshot/rows | Public scheduler compatibility lifecycle | compatibility facade only | Scheduler may own queue state and scheduler evidence timing, not execution authority. |
| `core/tasks/scheduler_execution_gateway.py` | Adds scheduler compatibility markers over `execution_gateway_runtime` | compatibility facade only | Does not import `core.runtime.executor`; keep as adapter surface. |
| `core/tasks/execution_gateway_runtime.py` | Calls task execution gateway and normalizes result payloads | compatibility facade only | Gateway normalization only; no runtime authority ownership. |
| `core/tasks/scheduler_core/task_scheduler_queue.py`, `worker_pool.py`, `task_dispatcher.py` | Queue, worker, dispatch primitives | coordination/orchestration logic | Safe future slimming candidates because they are already isolated modules. |
| `dispatch_*`, `queue_*`, `repo_state_helpers.py`, `public_task_record_helpers.py` | Repo state sync, blocked/unblocked routing, finalization, queue transitions | coordination/orchestration logic | Keep behavior intact; these are scheduler-owned lifecycle mutations, not runtime execution authority. |
| `command_step_helpers.py` | Handles command-like scheduler steps via `safe_subprocess_run` | compatibility facade only with legacy execution ownership risk | Uses governed facade and marks `canonical_executor`; retain guard that it never calls raw subprocess. |
| `simple_step_executor_helpers.py` | Legacy simple task file reads/writes/verifies | side-effect/helper risk | Contains direct guarded file writes. This is compatibility behavior, not runtime authority; defer slimming until covered by focused tests. |
| `atomic_edit_helpers.py` | Staged text write, backup, rollback helper for scheduler code edits | side-effect/helper risk | Direct file mutation helper. High-value future migration candidate, but do not touch during post-L4 stabilization. |
| `repair_injection_execution.py`, `repair_replay_continuation.py`, `retrying_repair_replay_state.py` | Retry repair step injection and replay continuation packaging | legacy execution ownership risk | Mutates task/runtime-state payloads and coordinates requeue. Preserve until governed repair/replay replacement is designed. |
| `runtime_resume_gate.py` | Blocks ready queue dispatch when runtime state requires review/blocker handling | coordination/orchestration logic | Good scheduler-owned safety gate; do not weaken. |
| `path_parser_helpers.py`, `pure_helpers.py`, `queue_formatting_helpers.py` | Stateless parsing/formatting helpers | safe future slimming candidate | Lowest-risk future extraction or cleanup candidates. |
| `llm_step_helpers.py`, `code_chain_tick_replay_bridge.py` | Compatibility bridge to task runner or step executor flows | legacy execution ownership risk | Keep behavior stable; future movement should route through governed task/repair facades. |
| `_zero_*` compatibility attachments in `scheduler.py` | Backward-compatible wrappers and late-bound methods | do-not-touch during post-L4 stabilization | Broad and fragile. Audit before changing; prefer adding tests before slimming. |
| `services/system_boot.py` | Constructs runtime object graph and evidence adapters | do-not-touch during post-L4 stabilization | Must remain bootstrap-only; no runtime governance execution logic should move here. |

## Remaining Risk List

- Direct file mutation still exists in scheduler compatibility helpers (`simple_step_executor_helpers.py`, `atomic_edit_helpers.py`, and legacy helper methods in `scheduler.py`). These paths are guarded or compatibility-scoped, but they are not yet fully represented as governed runtime mutation results.
- Retry repair injection mutates task steps and runtime state in scheduler-owned compatibility code. It does not claim runtime execution authority, but it duplicates some repair/replay coordination concerns that should eventually migrate behind a governed repair/replay facade.
- Command-like scheduler steps rely on `safe_subprocess_run`, which correctly delegates to runtime, but this remains a sensitive adapter. A future regression to raw subprocess would violate L4.
- Scheduler evidence is lifecycle evidence for queue/dispatch timing. It must not be confused with canonical runtime execution evidence.
- `scheduler.py` still carries broad `_zero_*` compatibility attachments. They are operationally risky to modify even when conceptually slim.

## No Current Bypass Found

The inspected scheduler surfaces did not show a remaining path that directly:

- imports or instantiates `core.runtime.executor.Executor`;
- calls `subprocess.run`, `subprocess.Popen`, `subprocess.check_output`, `subprocess.check_call`, or `os.system`;
- calls `build_runtime_evidence_record`;
- imports governed runtime execution session builders directly;
- owns recovery verification.

The command execution path found in `command_step_helpers.py` routes through `core.runtime.execution_gateway.safe_subprocess_run`, which is covered by the L4 freeze tests as a governed facade path.

## Safe Deferred Slimming Sequence

1. Add characterization tests for queue, worker, dispatch, simple-step, retry-repair, and review flows before moving code.
2. Extract stateless helper groups first: parser helpers, pure helpers, queue formatting, and queue transition helpers.
3. Stabilize adapter boundaries next: scheduler execution gateway, execution gateway runtime, repo state sync, and public task record helpers.
4. Move side-effect helpers only after governed equivalents are explicit: simple file writes, atomic edits, retry repair injection, and replay continuation.
5. Leave `_zero_*` compatibility wrappers for last. Treat each wrapper as a compatibility contract with before/after tests.
6. Keep `system_boot.py` as construction wiring only until a replacement boot facade is introduced and tested.

## Explicit Non-Goals

- No scheduler split in this audit.
- No `scheduler.py` refactor.
- No `system_boot.py` refactor.
- No production behavior change.
- No runtime authority behavior change.
- No new demo, UI, or capability-pack code.
- No weakening of L4 freeze, topology freeze, recovery, repair, or execution governance tests.

## Guardrails For Future Codex Work

- Treat `core.runtime.executor` as the only canonical command/subprocess execution authority.
- Keep scheduler as coordinator, not execution authority owner.
- Preserve governed metadata through every facade result.
- Do not introduce raw subprocess execution in scheduler or scheduler helpers.
- Do not let scheduler build canonical runtime evidence records; scheduler may emit scheduler lifecycle evidence only through its existing adapter.
- Do not let recovery verify without governed runtime lineage.
- Do not move runtime governance logic into `system_boot.py`.
- Before any slimming, run the L4 freeze tests and the focused scheduler characterization suite for the touched surface.

## Tests To Run Before Future Scheduler Slimming

- `python -m compileall core/runtime core/tasks`
- `python -m pytest tests/test_runtime_mainline_freeze_contract.py tests/test_runtime_topology_freeze_gate.py`
- `python -m pytest tests/test_runtime_execution_governance_enforcement.py tests/test_runtime_recovery_coordinator_contract.py`
- `python -m pytest tests/test_governed_runtime_execution_session.py tests/test_governed_runtime_replay_session.py tests/test_governed_runtime_continuation_session.py tests/test_governed_cross_session_handoff_contract.py`
- `python -m pytest tests/*scheduler*.py tests/*dispatch*.py tests/*queue*.py`
- For PowerShell, expand wildcard test lists with `Get-ChildItem` if pytest receives literal `*` paths.
