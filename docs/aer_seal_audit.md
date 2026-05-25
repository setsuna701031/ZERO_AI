# AER Seal Audit

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

This audit is a stabilization inventory, not a product or roadmap document. It records what appears sealed by contract tests, what is still held together by compatibility surfaces, and what should remain untouched until the next seal package is explicit.

## Current Seal Status

Current status: partially sealed runtime core.

The runtime has strong contract coverage in several high-risk areas, and the full test suite was green immediately before this audit (`3432 passed, 186 subtests passed`). That does not mean AER/runtime core is fully sealed. The current shape is closer to a compatibility-stabilized core: public behavior is constrained by tests, while several internal ownership lines still rely on wrapper layers, legacy aliases, and end-of-file patch tails.

The most stable areas are public runtime output, recovery compatibility ABI, deterministic memory snapshots, rollback contract ordering, recovery approval/review naming, and read-only recovery reports. The least sealed areas are cross-owner execution permission, audit completeness, replay/recovery determinism across the full scheduler path, mutation authority enforcement at all entry points, event vocabulary unification, lifecycle propagation, and the external runtime API.

## Sealed Contracts

### Public Runtime Output Sanitizer

Status: sealed at StepExecutor public output boundary.

Evidence:

- `core/runtime/runtime_execution_result.py` now centralizes public sanitization with `sanitize_runtime_public_output()` and `sanitize_runtime_execution_result_for_public()`.
- `core/runtime/runtime_execution_result_fields.py` defines forbidden public internal keys such as evidence adapter, boundary, hook, and fingerprint internals.
- `core/runtime/step_executor.py` applies final public output sanitization on `StepExecutor.execute_step()`.
- `tests/test_runtime_mainline_evidence_seal_contract.py` asserts forbidden keys are absent from top-level step result, nested `runtime_execution_result`, and adapter payload surfaces.
- `tests/test_runtime_execution_result_overlay_collapse.py` keeps `attach_runtime_execution_result(payload)` identity behavior intact.

Compatibility note:

- `RuntimeExecutionResult.to_dict()["evidence"]` remains available for legacy callers.
- The seal is public-output-only. Internal replay, recovery, scheduler, and evidence flows are intentionally not scrubbed by this contract.

### Recovery Compatibility ABI

Status: sealed for the immediate legacy import paths.

Evidence:

- `core/runtime/runtime_recovery_plan.py` re-exports or wraps `RuntimeRecoveryPlanner`.
- `core/runtime/runtime_recovery_audit.py` exposes `RuntimeRecoveryAudit`, `RuntimeRecoveryAuditRecord`, and `RuntimeRecoveryAuditRejected`.
- `core/runtime/runtime_recovery_policy.py` exposes `RuntimeRecoveryPolicyEvaluator`.
- `tests/test_runtime_recovery_approval_contract.py`, `tests/test_runtime_recovery_audit_contract.py`, and `tests/test_runtime_recovery_commit_gate_contract.py` cover current compatibility import paths and basic behavior.

Compatibility note:

- This is a facade/wrapper seal, not a completed recovery architecture consolidation.
- The ABI is stable enough for current tests, but implementation ownership remains split across planner, approval, policy, audit, execution contract, review, dry-run, and commit gate modules.

### Deterministic Memory Snapshot

Status: sealed for same-input snapshot fingerprint determinism.

Evidence:

- `core/runtime/runtime_memory_model.py` fingerprints snapshots from canonical normalized payloads.
- It sorts mapping keys, normalizes set/list/tuple shapes, handles datetime and path values, and excludes volatile identity/timestamp fields.
- `tests/test_runtime_kernel_phase5_convergence.py` covers immutable/deepcopy behavior and deterministic fingerprinting.

Compatibility note:

- Snapshot outward payloads can still expose `created_at`; fingerprinting excludes it.
- The seal is local to memory snapshot construction. It does not prove deterministic replay across scheduler, task runtime, recovery, or event bus paths.

### Rollback Provenance Ordering

Status: sealed for rollback contract ordering in recovery execution contracts.

Evidence:

- `core/runtime/runtime_recovery_execution_contract.py` orders rollback contracts by replay order, execution id, and contract id.
- The first runtime execution owner remains `step_executor.execute`; scheduler dispatch may exist as orchestration provenance but should not become execution root.
- `tests/test_runtime_recovery_execution_contract_contract.py` covers current rollback metadata expectations.

Compatibility note:

- This is contract report ordering, not a full provenance graph unification across task runner, task runtime, scheduler, and event streams.

### Semantic Vocabulary Freeze

Status: sealed for recovery approval granted naming.

Evidence:

- `core/runtime/runtime_recovery_approval.py` canonicalizes recovery approval reason aliases to `recovery_plan_approval_granted`.
- `core/runtime/runtime_recovery_execution_contract.py` and `core/runtime/runtime_recovery_execution_review.py` apply the same canonicalization at downstream report boundaries.
- `tests/test_runtime_recovery_execution_review_contract.py` expects `recovery_plan_approval_granted`.

Compatibility note:

- Old aliases such as `recovery_approval_granted` and `find_recovery_approval_granted` remain accepted as legacy vocabulary.
- This only freezes the currently failing recovery approval reason. Runtime-wide event and reason vocabularies are not yet fully frozen.

### Immutable Approval, Review, and Audit Reports

Status: sealed for current recovery report views.

Evidence:

- Approval, policy, plan, review, and audit compatibility reports return deep copies.
- Several report shapes set `read_only: True`.
- Tests mutate returned payloads/lists and assert the internal report remains unchanged:
  - `tests/test_runtime_recovery_approval_contract.py`
  - `tests/test_runtime_recovery_audit_contract.py`
  - `tests/test_runtime_recovery_commit_gate_contract.py`
  - `tests/test_runtime_recovery_execution_review_contract.py`

Compatibility note:

- Immutability is enforced mostly by copy-on-read and frozen dataclasses, not by one shared immutable report base class.
- The pattern is adequate for current contracts but still duplicated.

## Tests Passed But Architecture Still Needs Attention

### Compatibility Wrapper / Facade Mode

Current state:

- Many recent fixes intentionally use compatibility facades rather than moving core architecture.
- Recovery planner, policy, approval, audit, and execution contract modules expose old import paths while normalizing newer payload shapes.
- `RuntimeRecoveryApprovalReport = RuntimeRecoveryApprovalReportCompat` is a deliberate ABI hold.

Risk:

- Facades can hide duplicated semantics and make future refactors look like behavior changes.
- A later architecture pass should identify which wrapper becomes canonical and which old paths become permanent aliases.

### Alias / Legacy Import Path

Current state:

- Legacy import path preservation is now part of the runtime contract for recovery modules.
- `services/system_boot.py` also uses multi-path import fallback for planner, LLM client, agent loop, router, and verifier classes.

Risk:

- Import fallback is useful during stabilization but makes ownership unclear.
- Seal should eventually name canonical import roots and treat compatibility roots as explicit ABI adapters.

### Naming Canonicalization

Current state:

- Recovery plan approval naming is canonicalized.
- Runtime status, event, scheduler evidence phases, approval reasons, recovery reasons, mutation reasons, and lifecycle reasons still appear in multiple vocabularies.

Risk:

- Mixed vocabulary can break review/report consumers even when tests pass.
- A runtime-wide vocabulary registry is still missing.

### Public Output Boundary

Current state:

- StepExecutor public results are sanitized.
- Runtime public surface exists as `core/runtime/runtime_public_surface.py`, but most request APIs are intentionally unimplemented or not connected.
- `app.py` and `services/system_boot.py` still expose scheduler/task operations directly through CLI/system objects.

Risk:

- Current public boundary is strongest at `StepExecutor.execute_step()`, not at all entry points.
- CLI/system boot paths can still become accidental external APIs unless explicitly marked internal.

## Ownership Ambiguity

### Scheduler vs TaskRuntime vs StepExecutor

Observed state:

- `StepExecutor` owns step execution and public step result normalization.
- `TaskRuntime` owns state persistence, lifecycle updates, engineering execution/action records, replay helpers, and several governed runtime preview functions.
- `TaskRunner` bridges step execution, rollback, failure classification, and runtime state advancement.
- `Scheduler` owns orchestration, queue transitions, agent-loop fallback, and evidence adapter attachment.

Ambiguity:

- Scheduler dispatch is an orchestration owner, but step execution provenance must remain rooted in `step_executor.execute`.
- TaskRuntime contains many late-bound compatibility extensions and static helper assignments. This makes it difficult to distinguish runtime state authority from recovery/replay helper APIs.
- TaskRunner still has meaningful execution and rollback responsibilities, so StepExecutor is not the only execution boundary in practice.

Seal implication:

- Before AER seal, define an ownership table for:
  - execution root
  - orchestration owner
  - state persistence owner
  - retry/rollback owner
  - public result owner
  - evidence owner

### AgentLoop vs Runtime Executor

Observed state:

- `core/agent/agent_loop.py` can create or call `TaskRunner`, route tool calls, and produce repo-edit/code-chain behavior.
- `Scheduler` can call `agent_loop` through fallback paths.
- `services/system_boot.py` wires agent loop, scheduler, task runner, task runtime, and step executor together in one object graph.

Ambiguity:

- AgentLoop still has execution-adjacent behavior and code-chain repair/write paths.
- Runtime executor and scheduler ownership can be bypassed conceptually if AgentLoop is treated as a peer execution path rather than a request producer.

Seal implication:

- AER should define AgentLoop as either:
  - an intent/request producer that cannot execute directly, or
  - a governed runtime client with explicit capability grants.

### Recovery Planner vs Approval / Policy / Audit

Observed state:

- Recovery planning, policy evaluation, approval, audit, execution contract generation, review, dry-run, and commit gating are separate modules.
- Compatibility wrappers make those pieces interoperate for current tests.

Ambiguity:

- It is not yet explicit which module owns final recovery state transitions.
- Approval/report immutability is sealed, but recovery action authority and commit authority remain distributed.

Seal implication:

- Recovery needs a single authority map for:
  - plan construction
  - policy decision
  - approval gate
  - audit append
  - dry-run review
  - commit gate
  - execution prohibition / execution permission

## Possibly Unsealed Contracts

### Execution Permission Boundary

Risk: P0

Current evidence:

- There are many runtime execution authority modules and tests: execution gate, grant, lease, token, start, bridge, pending, controlled enqueue, admission policy, and governed action executor.
- These contracts exist, but the actual boot/runtime graph still wires scheduler, task runner, task runtime, step executor, and agent loop directly.

Gap:

- No single observed seal says: every execution path must pass one canonical permission boundary.
- AgentLoop, scheduler gateway, TaskRunner rollback paths, and StepExecutor handlers need one shared permission story.

### Audit Log Completeness

Risk: P0

Current evidence:

- Recovery audit, runtime audit registry/artifacts, mutation audit, evidence persistence, event sink, and scheduler evidence boundaries have tests.
- `runtime/mutations/mutation_audit.jsonl` is modified by tests, indicating real audit append side effects exist.

Gap:

- Completeness is not proven across all execution/mutation/recovery entry points.
- Audit records are present, but a seal needs a coverage matrix: which action classes must always emit audit, evidence, event, and provenance records.

### Replay / Recovery Determinism

Risk: P0

Current evidence:

- Deterministic memory snapshot and several replay/recovery contracts pass.
- Scheduler runtime tail regression covers several replay classes.
- Runtime event sourcing and deterministic replay layer tests exist.

Gap:

- Determinism is not yet proven end-to-end from scheduler dispatch through task runtime state, step execution result, event stream, evidence, recovery planning, and replay reconstruction.
- Timestamp handling is still present in event and bus paths.

### Mutation Authority Boundary

Risk: P0

Current evidence:

- Governed mutation runtime, mutation authority boundaries, mutation bypass enforcement, repair mutation scope gate, and governed repair tests exist.
- Runtime repair transaction proposal rejects runtime success shape and marks mutation authority as false.

Gap:

- Mutation pathways are broad: governed mutation runtime, repair execution, StepExecutor file handlers, AgentLoop code-chain paths, TaskRunner repair/rollback, and CLI task workflows.
- A seal needs proof that every write path is either governed or explicitly internal/test-only.

### Runtime Event Vocabulary

Risk: P1

Current evidence:

- `core/runtime/runtime_events.py` defines event classes.
- `core/runtime/runtime_event_bus.py`, event stream, event sink, event replay, and event normalizer have contract tests.
- Scheduler evidence boundary has deterministic orchestration phases.

Gap:

- Event names and reason codes are not yet under one registry.
- Some vocabularies are class-style event names, some are snake_case phases, and some are recovery/approval reason strings.

### Lifecycle Propagation

Risk: P1

Current evidence:

- Runtime lifecycle coordinator, pipeline, propagation, transition, status canonicalization, and scheduler tail tests exist.
- TaskRuntime carries many lifecycle/status helpers and patch-tail overrides.

Gap:

- Status/lifecycle propagation across scheduler, TaskRunner, TaskRuntime, StepExecutor, recovery, and replay needs one canonical transition map.
- Existing tests cover many cases but do not eliminate duplicate lifecycle owners.

### AER External / Public API

Risk: P1

Current evidence:

- `core/runtime/runtime_public_surface.py` exists and is intentionally mostly request-only or unimplemented.
- `app.py` exposes CLI commands that route directly into system/scheduler/task operations.
- `services/system_boot.py` builds a full internal object graph and returns it.

Gap:

- There is not yet a sealed AER external API boundary.
- Public API should not accidentally be defined by CLI convenience functions, system boot object attributes, or scheduler internals.

## Risk Sorting

### P0: Seal Before AER Core Seal

- Execution permission boundary: define and enforce the one canonical path required before execution.
- Audit log completeness: prove required audit/evidence/event/provenance records exist for every action class.
- Replay/recovery determinism: prove deterministic end-to-end behavior for scheduler-to-recovery paths, not only local snapshots.
- Mutation authority boundary: close all direct write/repair/code-chain paths behind governed authority.
- Public boundary escape audit: verify `app.py`, `services/system_boot.py`, scheduler gateways, and AgentLoop cannot bypass sealed runtime authority.

### P1: Stabilize After Seal

- Runtime event vocabulary registry and reason-code freeze.
- Lifecycle propagation map and duplicate owner reduction.
- Recovery architecture consolidation beyond compatibility wrappers.
- Public runtime API implementation behind `runtime_public_surface.py`.
- Shared immutable report/view base for approval, policy, audit, review, and dry-run reports.

### P2: Clean Before Demo / Packaging

- Reduce monkey-patch tail readability burden in `StepExecutor`, `TaskRunner`, and `TaskRuntime`.
- Normalize boot fallback comments and corrupted/help text in `app.py` and `services/system_boot.py`.
- Document legacy import aliases and facade modules.
- Separate internal CLI tools from future external runtime API docs.
- Add a compact seal manifest pointing to canonical tests and files.

## Remaining Blockers

1. No single execution authority gate is visibly mandatory across all runtime entry points.
2. Audit completeness is distributed and not summarized by one contract matrix.
3. Mutation authority still spans governed runtime, repair runtime, StepExecutor file handlers, AgentLoop code-chain behavior, and TaskRunner rollback behavior.
4. Runtime event and reason vocabulary is not globally frozen.
5. Lifecycle/status propagation still has multiple owners.
6. AER external/public API is not sealed; `runtime_public_surface.py` is mostly future-facing, while CLI/system boot expose internal surfaces.
7. Compatibility wrappers preserve ABI but obscure the eventual canonical recovery architecture.

## Recommended Next 3 Work Packages

### 1. Execution Authority Seal Matrix

Goal:

- Produce and enforce a matrix of every execution-capable entry point and the required permission gate.

Include:

- `StepExecutor.execute_step`
- `TaskRunner._run_one_step`
- `TaskRuntime` action and engineering execution helpers
- `Scheduler.tick` and scheduler execution gateway
- `AgentLoop` tool/code-chain paths
- CLI/app task commands
- governed action executor and mutation runtime

Expected output:

- A contract test that fails when any execution/write path lacks authority metadata, audit emission, and public output sanitization.

### 2. Audit / Evidence Completeness Seal

Goal:

- Define which records must be emitted for each runtime action class.

Minimum action classes:

- read-only execution
- write/mutation
- repair transaction
- rollback
- replay
- recovery plan/review/commit
- scheduler dispatch/requeue/cancel
- agent-loop initiated task/action

Expected output:

- One audit completeness contract that checks audit log, evidence refs, event stream, provenance, and public result shape together.

### 3. Runtime Vocabulary and Lifecycle Freeze

Goal:

- Create a canonical registry for runtime event types, phases, statuses, review reasons, approval reasons, and lifecycle transitions.

Include:

- scheduler evidence phases
- runtime event classes
- recovery reason strings
- mutation authority reasons
- task/runtime statuses
- public API status strings

Expected output:

- A vocabulary contract that rejects mixed aliases in public/runtime reports while preserving legacy alias intake at compatibility boundaries.

## What Not To Touch Yet

- Do not remove recovery compatibility wrappers or legacy import aliases until a replacement ABI map is agreed.
- Do not collapse scheduler, task runtime, task runner, and step executor ownership in the same patch as seal work.
- Do not connect `runtime_public_surface.py` directly to scheduler internals before execution authority and audit completeness are sealed.
- Do not broaden public sanitizer into replay/recovery/scheduler internals; the current sanitizer seal is intentionally public-output-only.
- Do not rewrite AgentLoop code-chain behavior until mutation authority and execution permission boundaries are defined.
- Do not normalize all event names opportunistically; first introduce a vocabulary registry and alias policy.
- Do not clean patch-tail monkey patches as a style refactor during seal work. Treat them as risk-bearing compatibility layers until covered by targeted migration tests.

## Bottom Line

AER/runtime core is not unsealed, but it is not ready for a final seal declaration either. The current state is a green, compatibility-stabilized runtime with several important local contracts sealed. The next seal work should focus on cross-entry-point authority, audit completeness, deterministic replay/recovery, mutation control, and public API boundaries rather than more single-point fixes.
