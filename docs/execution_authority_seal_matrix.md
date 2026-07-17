# Execution Authority Seal Matrix

Date: 2026-05-24

Scope reviewed:

- `core/runtime/`
- `core/tasks/`
- `core/agent/`
- `services/system_boot.py`
- `app.py`
- `tests/test_runtime_*.py`
- `tests/test_governed_*.py`
- `tests/test_*scheduler*.py`

This matrix is an audit of current execution-capable and mutation-capable entry points. It does not propose feature expansion and does not treat synthetic metadata as a seal. A path is only "sealed" when a contract test makes the authority, audit/evidence/provenance, and public output behavior explicit.

Inventory positioning: authority metadata is not enforcement. This package is an inventory-only contract for pre-execution authority coverage; it must not add fake authority metadata or change runtime behavior.

## Current Authority Model

Current model: distributed authority with local gates.

There is no single mandatory authority gate that every execution-capable path must pass before running code, mutating files, dispatching tasks, replaying state, or committing recovery/mutation work. Instead, authority is distributed across:

- `StepExecutor` handler guardrails and final public output sanitization.
- `TaskRunner` audit logging, mutation boundary attachment, rollback handling, and failure/retry logic.
- `TaskRuntime` lifecycle/state ownership, read-only command gates, replay/evidence registry helpers, and engineering execution records.
- `Scheduler` queue/dispatch ownership and scheduler evidence emission.
- `AgentLoop` intent/tool/repo-edit routing and code-chain visibility scaffolding.
- Governed mutation/recovery/repair modules with local approval, scope, dry-run, commit, and rollback contracts.
- CLI/system boot surfaces that expose scheduler and task operations directly.

The strongest current seals are local:

- StepExecutor public output sanitizer.
- Scheduler evidence adapter/boundary contracts.
- Governed runtime action executor as a data-only/dry-run/review gate.
- Governed mutation runtime happy/rollback paths.
- Recovery approval/review/audit/report immutability and compatibility ABI.

The missing AER seal is cross-entry-point: every execution or mutation route should either prove it passed a canonical authority boundary or be classified as explicitly read-only/internal.

## Entry Point Matrix

| Area | File | Function / class | Action type | Current authority check | Current audit / evidence / provenance emission | Public output sanitizer coverage | Bypass risk | Seal status | Required next action |
|---|---|---|---|---|---|---|---|---|---|
| StepExecutor direct step | `core/runtime/step_executor.py` | `StepExecutor.execute_step` | execute / write / mutate depending on step type | Local handler validation, runtime boundary helpers, mutation-specific handlers, selective activation layers; no single global authority token required at method entry | Execution trace, runtime event stream, adapter payload, evidence adapter hooks when configured | Covered by final `sanitize_runtime_public_output()` wrapper for public result | Direct callers can invoke execution without scheduler/task authority metadata | partially sealed | P0: contract requiring authority classification for every side-effect step type before execution |
| StepExecutor batch | `core/runtime/step_executor.py` | `StepExecutor.execute_steps` | execute aggregate | Delegates to `execute_step`; aggregate logic owns result merging | Merged execution traces and runtime event stream | Covered indirectly when each step and aggregate result are sanitized | Batch entry can obscure which step had authority | partially sealed | P0: batch contract must preserve per-step authority decisions and deny mixed unauthorized side effects |
| StepExecutor write handler | `core/runtime/step_executor.py` | write/ensure file handlers | write / mutate | Workspace/path guardrails and handler-specific checks; governed mutation authority is not uniformly mandatory | Runtime execution result, provenance in some persistence writes, possible mutation boundary from TaskRunner after step | Public result sanitized after handler return | Direct handler route can write without TaskRunner mutation boundary if called outside normal runner | partially sealed | P0: side-effect handler contract must require authority source, audit ref, and rollback/readiness classification |
| StepExecutor append handler | `core/runtime/step_executor.py` | append file handler | write / mutate | Handler-specific path validation | Runtime result/provenance where persistence service is used | Public result sanitized after handler return | Same as write handler; append can be lower visibility than patch | partially sealed | P0: include append in side-effect authority test matrix |
| StepExecutor patch handlers | `core/runtime/step_executor.py` | apply patch / unified diff handlers | mutate / rollback-capable | Backup/path/diff handling and code-chain repair shims; not one global permission gate | Backup/provenance for patch paths, runtime result, downstream TaskRunner mutation boundary | Public result sanitized after handler return | Patch path is high-risk and has multiple shim versions | partially sealed | P0: require governed mutation or explicit internal repair authority before patch apply |
| StepExecutor command handlers | `core/runtime/step_executor.py` | run python / command / shell handlers | execute | Safety guard / command guard behavior exists, but method-entry authority is not globally enforced | Runtime execution result, stdout/stderr evidence fields, execution trace | Public result sanitized after handler return | Direct command execution path can bypass scheduler-level policy | partially sealed | P0: command execution must require execution grant or read-only command gate classification |
| TaskRunner step bridge | `core/runtime/task_runner.py` | `TaskRunner._run_one_step` | execute / retry / dispatch-to-step | Uses failure policy, side-effect step classification, mutation runtime integration, rollback conditions | `AuditLogger.log_event`, runtime state updates, mutation boundary attachment, execution trace propagation | Not the primary sanitizer owner; relies on StepExecutor and final result normalization | TaskRunner can execute side-effect steps but authority is partly inferred after execution | partially sealed | P0: assert pre-execution authority decision is present before side-effect step execution |
| TaskRunner rollback path | `core/runtime/task_runner.py` | rollback restore handling | rollback / mutate | `should_rollback_after_failed_verify`, repair context rollback availability | Rollback action records via `TaskRuntime.record_rollback_restore_action`, audit events | Public output depends on caller and result finalization | Rollback can mutate filesystem/state and must not be treated as only failure handling | partially sealed | P0: rollback authority contract must require rollback owner, rollback snapshot, audit ref, and provenance |
| TaskRunner retry/failure handling | `core/runtime/task_runner.py` | failure classification / retry handling | execute / dispatch / recover | Failure policy and retry strategy checks | Audit events, task/runtime state updates, execution trace | Partial through runtime/task result finalization | Retry can re-enter execution path without a fresh authority check | partially sealed | P0: retry re-entry must carry original authority or require renewed authority |
| TaskRunner mutation boundary attachment | `core/runtime/task_runner.py` | `_attach_mutation_boundary_after_step` | audit / mutate metadata | Optional governed mutation integration after step execution | Mutation boundary, mutation reconciliation, repair history | Output later sanitized only at public boundaries | Authority is attached after mutation, not guaranteed before mutation | partially sealed | P0: move proof requirement to pre-execution contract without refactoring implementation yet |
| TaskRuntime lifecycle | `core/runtime/task_runtime.py` | advance / mark finished / mark failed / save state | lifecycle / write state | TaskRuntime is state owner; status transition helpers and lifecycle contracts exist | Runtime state persistence, engineering execution records, lifecycle/evidence reports in helpers | Not public sanitizer owner | Lifecycle writes can be invoked by multiple owners | partially sealed | P1: lifecycle owner contract with allowed callers and transition evidence requirements |
| TaskRuntime engineering execution helpers | `core/runtime/task_runtime.py` | engineering action/session helpers | write state / audit | Internal helper conventions; some guarded by engineering execution normalization | Engineering execution/action records, immutable journal previews | Not public sanitizer owner | Large patch-tail surface makes caller authority hard to see | partially sealed | P1: inventory allowed callers and convert to explicit facade later |
| TaskRuntime read-only command gate | `core/runtime/task_runtime.py` | `run_readonly_command_execution_gate` / `execute_readonly_command_from_gate` | read / execute read-only | Read-only command parser/deny rules and safe subprocess wrapper | Evidence record, registry hooks, replay lineage helpers | Not StepExecutor public sanitizer; returns local gate payload | Safer than generic command, but external callers may confuse read-only execute with general execute authority | partially sealed | P0: contract that read-only gate cannot mutate and cannot grant mutation authority |
| TaskRuntime replay/evidence registry | `core/runtime/task_runtime.py` | `RuntimeEvidenceRegistry`, replay/evaluation helpers | replay / read / evaluate | Evidence id lookup and replayability checks | Evidence registry records, execution ancestry, replay lineage, validation reports | Not public sanitizer owner | Determinism/audit completeness local to registry, not scheduler end-to-end | partially sealed | P1: end-to-end replay determinism contract from execution result to registry replay |
| TaskRuntime mutation readiness helpers | `core/runtime/task_runtime.py` | mutation readiness evaluation helpers | read / authorize future mutation | Evidence-based readiness scoring; returns deny/allow-future decisions | Evaluation payloads, governance reasons | Not public sanitizer owner | "allow future governed mutation" can be mistaken for authority grant | partially sealed | P0: contract that readiness does not execute and does not grant direct mutation authority |
| Scheduler queue lifecycle | `core/tasks/scheduler.py` | `enqueue`, `enqueue_task`, requeue/cancel helpers | dispatch / lifecycle | Queue status rules and scheduler ownership | Scheduler evidence adapter/boundary emits enqueue/dequeue/requeue/cancel | Scheduler public status tests block evidence internals | Queue operations can become public control plane without authority model | partially sealed | P1: queue operation authority policy for external callers |
| Scheduler tick | `core/tasks/scheduler.py` | `Scheduler.tick` | dispatch / execute via runner/agent loop | Dispatchability/status checks; no one global AER execution grant | Scheduler evidence emitted for dispatch and lifecycle; task results carry traces | Public scheduler outputs have some evidence-internal seals | Tick is a broad external entry point through system/app | partially sealed | P0: tick must prove each dispatched execution path passed execution authority |
| Scheduler run-one-step | `core/tasks/scheduler.py`, `core/runtime/task_scheduler.py` | `run_one_step` | execute / dispatch | Delegates to TaskRunner/StepExecutor/gateway depending path | Scheduler/task runtime evidence depending configured path | Sanitizer depends on downstream StepExecutor | Multiple implementations and compatibility paths | partially sealed | P0: one contract comparing all run-one-step routes for authority/audit parity |
| Scheduler execution gateway | `core/tasks/scheduler_execution_gateway.py`, `core/tasks/execution_gateway.py`, `core/tasks/execution_gateway_runtime.py` | `run_scheduler_execution_gateway` | execute / gateway dispatch | Gateway metadata such as authority source/scope/status exists in some layer | Gateway result metadata, mismatch evidence, scheduler gateway flags | Depends on executor result sanitizer | Gateway can call `execute_step` directly and authority metadata may be descriptive rather than enforced | partially sealed | P0: gateway authority metadata must be required input/output, not just output decoration |
| Scheduler evidence boundary | `core/runtime/scheduler_evidence_boundary.py`, `core/runtime/scheduler_evidence_adapter.py` | evidence emitters | audit / evidence | Boundary validates event shape and deterministic sequence | Scheduler lifecycle evidence | Not a sanitizer; internal evidence hidden by public boundary tests | Evidence exists for scheduler lifecycle, not necessarily execution authority | sealed for scheduler evidence only | P1: link scheduler evidence refs to execution authority decisions |
| AgentLoop main run | `core/agent/agent_loop.py` | `AgentLoop.run` | intent / tool / possible mutation route | Intent classification, route guards, repair scope preflight | Tool traces, code-chain visibility/audit scaffolding for some paths | Not covered by StepExecutor sanitizer unless routed through runtime | AgentLoop can route to repo-edit/code-chain paths outside scheduler authority | partially sealed | P0: AgentLoop must be classified as request producer or governed runtime client |
| AgentLoop tool path | `core/agent/agent_loop.py` | `_execute_tool_call_plan` | execute / tool side effects | Tool registry/tool executor policy, not AER authority gate | Tool call trace events | Not runtime public sanitizer | Tool side effects depend on tool implementation, outside runtime seal | unsealed | P0: require tool authority envelope for side-effect tools |
| AgentLoop forced repo-edit | `core/agent/agent_loop.py` | `_try_force_repo_edit_route` | mutate / repair | Delegates to repo edit bridge/tool; local missing-path and scope preflight exists | Forced repo edit execution log and tool call metadata | Not runtime sanitizer owner | Direct repo-edit bridge can bypass scheduler/StepExecutor authority model | unsealed | P0: route forced repo-edit through governed mutation authority or mark internal-only with contract |
| AgentLoop code-chain visibility | `core/agent/agent_loop.py` | `_prepare_code_chain_patch_visibility`, `_finalize_code_chain_patch_visibility`, scoped patch apply | write / mutate / audit | Persistence service provenance and scope checks in parts; no single mutation authority gate | Backup, diff, audit artifacts, provenance payloads | Not runtime sanitizer owner | Some code-chain patch apply writes occur in AgentLoop itself | unsealed | P0: prohibit direct write or require governed mutation authority before scoped patch apply |
| Governed mutation runtime | `core/runtime/governed_mutation_runtime.py`, `core/runtime/mutation_gateway.py` | governed mutation mainline/runtime | mutate / rollback / audit | Mutation approval mode, rollback root, verification checks | Evidence artifacts, rollback snapshot, runtime execution result | Public sanitizer applies when surfaced through StepExecutor; direct API keeps evidence by design | Direct API is intentionally mutation-capable; authority must be explicit | partially sealed | P0: contract direct governed mutation API requires approval/rollback/audit/evidence fields |
| Governed repair execution | `core/runtime/governed_repair_execution.py`, `core/runtime/governed_repair_api.py` | `execute_governed_repair_transaction`, repair mutation API | mutate / repair / rollback | Runtime legality, approval mode, optional recovery gate hook, mutation topology | Mutation pipeline result, metadata/evidence, rollback root | Direct API not necessarily public-sanitized | `approval_mode=AUTO` test paths are convenient but high-risk for AER external use | partially sealed | P0: distinguish test/internal auto approval from external authority |
| Repair transaction bridge | `core/runtime/repair_transaction_execution_bridge.py` | committed repair transaction execution | mutate / repair / recover continuation | Requires committed transaction fields, approval mode, controlled mutation bridge metadata in some paths | Lineage, audit id, replay id, mutation summary, continuation metadata | Direct API not StepExecutor-sanitized | Bridge can execute committed mutations if called directly with permissive approval | partially sealed | P0: require controlled mutation bridge or explicit repair authority for direct bridge calls |
| Runtime repair transaction apply | `core/tasks/runtime_repair_apply_transaction.py` | transaction apply/commit helpers | mutate / rollback / audit | Review token/session/commit helpers, allowed boundaries, sandbox operations | Audit events, artifacts, lineage, provenance, replay digest | Not StepExecutor sanitizer | Large helper surface mixes preview, commit, sandbox apply, and rollback | partially sealed | P0: separate preview-only contracts from mutation-capable commit contracts |
| Recovery planner/policy/approval/audit | `core/runtime/runtime_recovery_plan.py`, `runtime_recovery_policy.py`, `runtime_recovery_approval.py`, `runtime_recovery_audit.py` | planner/evaluator/audit reports | recover planning / review | Read-only compatibility reports, policy gates, approval reports | Immutable reports, audit records | Not public sanitizer owner | Planning approval can be mistaken for execution permission | sealed for report ABI, not execution | P0: explicit contract that recovery approval report does not execute recovery |
| Recovery execution contract/review | `core/runtime/runtime_recovery_execution_contract.py`, `runtime_recovery_execution_review.py` | execution contract builder/reviewer | recover / rollback contract generation | Contract generation only, read-only reports, no execution flags | Contract/review reports, risk summaries | Not public sanitizer owner | Contract may be interpreted as executable if caller ignores `executes_* = False` | partially sealed | P0: assert recovery execution contracts never execute and require separate commit gate |
| Recovery commit gate | `core/runtime/runtime_recovery_commit_gate.py` | commit gate report | recover commit gating | Dry-run/read-only checks and commit gate violations | Commit gate report with read-only flag | Not public sanitizer owner | Gate semantics need linkage to actual execution authority | partially sealed | P0: commit gate must be required before any recovery mutation path |
| Replay reconstruction | `core/runtime/runtime_recovery_evidence_replay_reconstruction.py`, replay/recovery bridge modules | replay reconstruction helpers | replay / recover | Evidence/replay validation helpers | Replay/reconstruction reports and evidence attachments | Not public sanitizer owner | Determinism is local; execution graph linkage incomplete | partially sealed | P1: end-to-end deterministic replay contract |
| Runtime public surface | `core/runtime/runtime_public_surface.py` | `submit_runtime_task`, `request_runtime_*`, `query_runtime_status` | external API / request | Request-only connector for task submit; most mutation/replay/recovery APIs unimplemented | Connector request envelope only | No execution output yet | Low current risk because mostly not connected; high future risk if wired directly | partially sealed as not-connected | P1: implement only behind authority/audit matrix |
| System boot object graph | `services/system_boot.py` | `ZeroSystem`, `tick`, `run_until_idle`, task methods | dispatch / execute via scheduler | Constructs scheduler/task runtime/task runner/step executor/agent loop with evidence adapters; method calls delegate directly | Evidence adapters attached; health exposes boot state | Returned `raw_result` may include scheduler output; relies on downstream sanitizers | System object exposes internals as a de facto API | partially sealed | P0: classify ZeroSystem as internal facade or wrap public methods with authority/audit policy |
| CLI command mode | `app.py` | task create/submit/run/tick/loop commands | external dispatch / execute | CLI delegates to system/scheduler; no separate AER authority gate | Whatever scheduler/runtime emits; CLI prints JSON | Relies on downstream sanitization and display helpers | CLI can trigger scheduler execution directly | unsealed | P0: external CLI execution commands need authority classification before AER seal |
| L5 background loop | `app.py` | `_l5_create_task_suggestion`, background loop | external-ish dispatch / enqueue suggestion | Creates suggestion task with `requires_approval=True`; does not submit/run | Scheduler create task output | Not execution output | Background task creation is easy to confuse with autonomous execution | partially sealed | P1: contract suggestion creation cannot submit or execute without approval |

## Known Bypass Risks

### P0

- Direct `StepExecutor.execute_step()` callers can execute side-effect steps without a scheduler/task authority envelope.
- Scheduler execution gateway can call `execute_step` directly while authority metadata is currently not proven to be mandatory input.
- `TaskRunner` attaches mutation boundary metadata after StepExecutor returns; this does not prove pre-execution mutation authority.
- AgentLoop has repo-edit/code-chain paths that can write or prepare patch artifacts outside the scheduler/task runtime/StepExecutor authority chain.
- CLI and `ZeroSystem` expose scheduler execution paths directly and may become accidental public API.
- Governed repair/mutation direct APIs are intentionally mutation-capable; external use needs explicit approval/rollback/audit/evidence requirements.

### P1

- Lifecycle/status propagation has multiple owners: scheduler, TaskRunner, TaskRuntime, recovery, replay, and event helpers.
- Runtime event/evidence/audit records are present but not joined by one completeness contract.
- Recovery approval/review/contract reports are read-only, but callers still need a separate execution/commit authority contract.
- Runtime public surface is not connected now, but future wiring could bypass internal gates if connected to scheduler directly.

### P2

- Patch-tail compatibility layers in StepExecutor, TaskRunner, TaskRuntime, and AgentLoop make authority review difficult.
- Boot fallback imports and CLI helper text should be cleaned after seal-critical contracts are fixed.
- Legacy aliases should be documented in a public ABI map, not inferred from tests.

## Required P0 Contracts

1. Side-effect StepExecutor authority contract.
   - For `write_file`, `append_file`, `apply_patch`, `apply_unified_diff`, `run_python`, `command`, and shell-like steps.
   - Must assert each side-effect result includes a real authority decision source, audit/evidence ref, provenance owner, and public sanitizer coverage.
   - Must reject fake authority metadata that is only added after execution.

2. Scheduler gateway authority contract.
   - For `Scheduler.tick`, `Scheduler.run_one_step`, and `run_scheduler_execution_gateway`.
   - Must assert scheduler dispatch is orchestration authority only, while execution authority is owned by runtime/StepExecutor grants.
   - Must require gateway authority metadata to be present before execution and preserved after execution.

3. TaskRunner mutation/rollback preflight contract.
   - Must prove mutation and rollback authority are decided before filesystem/state mutation.
   - Must cover retry re-entry and rollback-after-failed-verify paths.

4. AgentLoop no-direct-mutation contract.
   - Must classify AgentLoop as request producer or governed runtime client.
   - Must fail if AgentLoop directly writes repo/code-chain patch content without controlled mutation authority.
   - Should preserve existing functionality until a governed bridge is available; the first contract can be audit-only/xfail-free by inventorying paths.

5. External surface authority contract.
   - Must classify `app.py` and `services/system_boot.py` execution methods as internal or guarded public surfaces.
   - Must assert public/external methods cannot execute without an authority envelope once AER seal is declared.

6. Governed mutation/recovery execution contract.
   - Must distinguish report/readiness/approval from actual execution permission.
   - Must require approval, rollback snapshot, audit/evidence, and recovery commit gate before mutation/recovery execution.

## Recommended Next Implementation Package

Package: `execution_authority_inventory_contract`.

Purpose:

- Add a minimal contract test that inventories execution-capable entry points without changing behavior.
- The test should not require new fake metadata and should not assert the final desired model yet.
- It should make the current risk visible and stable so follow-up patches can close one path at a time.
- Boundary: public output sanitizer do not mix into this package.
- Boundary: recovery ABI do not mix into this package.

Suggested test file:

- `tests/test_execution_authority_seal_matrix_contract.py`

Suggested assertions:

- Known entry point list exists and maps each path to an action type.
- Every side-effect-capable entry point has a current seal status and required next action in the matrix document.
- The matrix contains all required P0 surfaces:
  - `StepExecutor.execute_step`
  - `StepExecutor.execute_steps`
  - `TaskRunner._run_one_step`
  - TaskRunner rollback path
  - TaskRuntime read-only command gate
  - `Scheduler.tick`
  - `Scheduler.run_one_step`
  - scheduler execution gateway
  - `AgentLoop.run`
  - AgentLoop tool path
  - AgentLoop repo-edit/code-chain path
  - governed mutation runtime
  - repair transaction execution bridge
  - recovery commit gate
  - `ZeroSystem.tick`
  - `app.py` task run/tick command paths
  - `runtime_public_surface.py`

Follow-up implementation order:

1. Add inventory-only test for matrix completeness.
2. Add StepExecutor side-effect pre-authority contract.
3. Add Scheduler/TaskRunner propagation contract for authority/audit/provenance.
4. Add AgentLoop no-direct-mutation contract.
5. Add external surface guard contract.

## What NOT To Change Yet

- Do not touch public runtime output sanitizer.
- Do not touch recovery ABI compatibility wrappers.
- Do not change AgentLoop behavior in this work package.
- Do not merge scheduler, task runtime, task runner, and step executor.
- Do not add fake authority metadata just to satisfy an audit.
- Do not connect `runtime_public_surface.py` directly to scheduler internals.
- Do not remove legacy scheduler execution gateway metadata until a replacement authority contract exists.
- Do not treat approval/readiness reports as execution permission.
- Do not refactor patch-tail compatibility layers as cleanup during P0 seal work.

## Seal Decision

Execution authority is not sealed yet.

Current tests show many local guards are working, but AER seal requires an end-to-end authority proof. The immediate next step should be an inventory-only contract, followed by narrow pre-execution authority contracts for StepExecutor side-effect handlers, Scheduler gateway dispatch, TaskRunner rollback/retry, AgentLoop mutation-capable paths, and external CLI/system surfaces.
