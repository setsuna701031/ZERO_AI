# Runtime Freeze Candidate Validation - Phase 4-G

Date: 2026-05-18

Source documents and enforcement tests:

- `docs/runtime_kernel_boundary_contract.md`
- `docs/runtime_mainline_freeze_audit.md`
- `docs/runtime_freeze_guardrails.md`
- `tests/test_runtime_boundary_imports.py`
- `tests/test_runtime_mutation_authority_boundaries.py`

This document validates whether the current ZERO Runtime Kernel governance stack can prevent architecture drift before declaring Runtime Kernel Freeze Candidate. It is documentation-only and does not implement APIs, refactor `scheduler.py`, move files, change runtime behavior, or clean existing warnings.

## Validation Summary

Current readiness classification: `freeze_candidate`

The Runtime Kernel is not frozen, but the current governance stack is strong enough to treat it as a freeze candidate if the protected smoke pack passes. Boundary import tests prevent the most important direct external imports. Mutation authority tests prevent obvious external rollback, mutation, recovery, patch apply, approval, repair transaction, forced execution, and override calls. The freeze guardrails define when changes require smoke coverage, rollback plans, or review blocks.

There are no current hard blockers to freeze-candidate status based on the protected governance stack. Remaining work such as public facade implementation, broader recovery-specific smoke coverage, warning cleanup, and future authority annotations is useful but not a blocker for declaring a candidate.

## 1. Boundary Protection

### Can External Layers Directly Import Scheduler Internals?

Not without failing `tests/test_runtime_boundary_imports.py`.

Protected external-facing layers:

- `core/capabilities/`
- `core/agent/`
- `core/planning/`
- `services/`

Forbidden scheduler targets include:

- `core.tasks.scheduler`
- `core.tasks.scheduler_core`

The only explicit exception is `services/system_boot.py` importing `core.tasks.scheduler.Scheduler` as the bootstrap/runtime construction owner. That exception is intentionally narrow and must not expand into general service-layer scheduler access.

Validation result: external layers cannot newly import scheduler internals without producing a clear `path:line: imported_module` failure.

### Can External Layers Directly Import Mutation, Recovery, or Rollback Internals?

Not for the protected import targets without failing `tests/test_runtime_boundary_imports.py` or the broader authority radar in `tests/test_runtime_mutation_authority_boundaries.py`.

Protected import targets include:

- `core.runtime.mutation_runtime_pipeline`
- `core.runtime.mutation_boundary`
- `core.runtime.mutation_patch_apply`
- `core.runtime.rollback_verification`
- `core.runtime.runtime_recovery_coordinator`
- `core.runtime.runtime_recovery_policy`
- `core.runtime.runtime_recovery_commit_gate`

The mutation authority radar also detects direct imports whose names include mutation, rollback, recovery, patch apply, commit gate, approval, repair transaction, forced execution, bypass, unsafe apply, or override authority terms.

Validation result: external-facing layers cannot directly import these protected internals without a boundary failure.

## 2. Authority Protection

### Can Agent, Capability, or Planning Layers Directly Perform Rollback, Mutation, Recovery, Patch Apply, or Override?

Not by obvious direct calls without failing `tests/test_runtime_mutation_authority_boundaries.py`.

The authority radar uses AST parsing and checks direct call expressions, not comments or strings. It guards against calls involving:

- rollback;
- mutation;
- recovery;
- patch apply;
- atomic edit/apply;
- repair execution;
- repair transaction;
- recovery coordinator/policy/commit gate/execution;
- approval;
- forced execution;
- override;
- bypass;
- unsafe apply.

Current Code Chain rollback authority has already been isolated: `core/agent/agent_loop.py` now requests restore through `core.runtime.code_chain_patch_restore.request_code_chain_patch_restore`, so the agent no longer owns direct rollback execution.

Validation result: external layers may request governed runtime work, but obvious direct authority calls are blocked by regression coverage.

## 3. Scheduler Pollution Prevention

Current protections preventing `scheduler.py` from becoming public API again:

- The Runtime Kernel Boundary Contract states that `scheduler.py` is not the public runtime API.
- The Freeze Guardrails require new external access to go through governed runtime surfaces.
- `tests/test_runtime_boundary_imports.py` blocks external-facing layers from importing `core.tasks.scheduler` or `core.tasks.scheduler_core`, except the explicit `services/system_boot.py` bootstrap exception.
- The guardrails classify scheduler private methods, actual enqueue primitive execution, scheduler_core helpers, dispatch/finalize routing, worker release routing, queue hygiene, pending repair lifecycle, replay/retry coordination, and compatibility bindings as protected scheduler ownership.
- Changes that expose scheduler internals, add public scheduler access, or alter compatibility binding order must be blocked until reviewed.

Validation result: the current stack prevents accidental scheduler public-API expansion in external-facing layers covered by the import test.

## 4. Self-Edit Protection

Current protections preventing future self-edit runtime from directly mutating internals:

- The Boundary Contract requires self-edit to use governed mutation only.
- The Freeze Guardrails forbid direct internal mutation from agent, planner, services, plugin, capability pack, UI, and remote orchestration layers.
- `tests/test_runtime_mutation_authority_boundaries.py` blocks obvious direct authority calls from agent, capability, planning, and services layers.
- `tests/test_runtime_boundary_imports.py` blocks direct imports of scheduler and high-risk mutation/recovery internals.
- The Code Chain rollback path has been moved behind runtime-owned `request_code_chain_patch_restore`.

Self-edit must preserve:

- request-only agent/planner behavior;
- policy and guard checks;
- approval when required;
- rollback for repository-changing edits;
- verification before success;
- audit/evidence for proposal, policy, approval, mutation, rollback, verification, and final status.

Validation result: current external-facing self-edit paths are guarded against direct mutation authority drift.

## 5. Protected Smoke Pack

These tests must pass before runtime kernel changes are considered safe:

1. `tests/test_runtime_boundary_imports.py`
2. `tests/test_runtime_mutation_authority_boundaries.py`
3. `tests/test_repair_chain_runtime.py`
4. `tests/test_scheduler_parser_helpers.py`

Required command pack:

```text
python -m pytest tests/test_runtime_boundary_imports.py -q
python -m pytest tests/test_runtime_mutation_authority_boundaries.py -q
python -m pytest tests/test_repair_chain_runtime.py -q
python -m pytest tests/test_scheduler_parser_helpers.py -q
```

If `python` is not on PATH, use the known passing bundled Python executable for this workspace.

## 6. Current Freeze Readiness

Classification: `freeze_candidate`

Rationale:

- Boundary contract exists and defines public, internal mutation, and legacy compatibility surfaces.
- Mainline freeze audit classifies protected flows and identifies stable contract candidates.
- Freeze guardrails define protected flows, sensitive modules, smoke requirements, rollback-plan rules, scheduler freeze rules, and self-edit freeze rules.
- Static import enforcement blocks external-facing layers from importing scheduler and high-risk runtime internals.
- Static authority radar blocks obvious direct mutation/rollback/recovery/patch/override authority calls from external-facing layers.
- Code Chain rollback authority has been isolated into a runtime-owned helper.
- The protected smoke pack has passed in the recent Phase 4-F run and must pass again for this validation.

This is not `frozen` because the public runtime facade is still proposed rather than implemented, recovery remains internal/transitional, and compatibility surfaces still exist. Those facts do not block freeze-candidate status because the candidate is about locking current boundaries and preventing drift, not declaring final API completion.

## 7. Remaining Blockers

There are no current hard blockers to declaring Runtime Kernel Freeze Candidate, provided the protected smoke pack passes.

Not blockers for candidate status:

- existing `datetime.utcnow()` deprecation warnings;
- lack of a new public runtime API implementation;
- future authority annotations;
- future HTTP/RPC/CLI/UI mappings;
- broader recovery-specific smoke expansion;
- cleanup of legacy compatibility surfaces.

These items should be tracked separately and must not be mixed into freeze-candidate validation.

## 8. Freeze Candidate Declaration Criteria

Declare `Runtime Kernel Freeze Candidate` only when all of the following are true:

- `docs/runtime_kernel_boundary_contract.md` exists and remains the SSOT for runtime boundaries.
- `docs/runtime_mainline_freeze_audit.md` classifies protected mainline flows.
- `docs/runtime_freeze_guardrails.md` defines protected flows, tests, sensitive modules, change rules, scheduler rules, and self-edit rules.
- `tests/test_runtime_boundary_imports.py` passes.
- `tests/test_runtime_mutation_authority_boundaries.py` passes.
- `tests/test_repair_chain_runtime.py` passes.
- `tests/test_scheduler_parser_helpers.py` passes.
- External-facing layers cannot import protected scheduler/runtime internals.
- External-facing layers cannot perform obvious direct mutation/rollback/recovery/patch/override authority calls.
- Scheduler remains isolated from public API expansion.
- Self-edit remains request-only and uses governed runtime authority paths.
- Runtime mutation-sensitive changes have a rollback plan.
- No production behavior changes, scheduler refactors, file moves, broad cleanup, or warning cleanup are bundled into the declaration.

## 9. Non-Goals

This validation does not:

- implement runtime APIs;
- implement wrappers;
- change runtime behavior;
- refactor `scheduler.py`;
- move files;
- clean `datetime.utcnow()` warnings;
- remove compatibility bindings;
- declare the kernel permanently frozen;
- approve direct external access to runtime internals.
