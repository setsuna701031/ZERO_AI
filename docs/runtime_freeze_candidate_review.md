# Runtime Freeze Candidate Review - Phase 4-I

Date: 2026-05-18

Source documents and enforcement tests:

- `docs/runtime_kernel_boundary_contract.md`
- `docs/runtime_mainline_freeze_audit.md`
- `docs/runtime_freeze_guardrails.md`
- `docs/runtime_freeze_candidate_validation.md`
- `docs/runtime_freeze_hardening_plan.md`
- `tests/test_runtime_boundary_imports.py`
- `tests/test_runtime_mutation_authority_boundaries.py`

This is the final review before declaring ZERO Runtime Kernel Freeze Candidate as a protected baseline. It does not implement APIs, refactor `scheduler.py`, move files, change runtime behavior, or clean existing warnings.

## 1. Final Freeze Candidate Verdict

Final verdict: `freeze_candidate`

The current Runtime Kernel governance stack is ready to be declared a protected Freeze Candidate Baseline if the required protected smoke pack passes. The kernel is not declared permanently frozen: public runtime facade implementation, recovery facade design, broader authority annotations, and compatibility cleanup remain future work. None of those items are blockers for a freeze-candidate baseline.

## 2. Protected Runtime Paths

| Runtime path | Status | Review note |
| --- | --- | --- |
| repair | `freeze_protected`, `compatibility_sensitive`, `transitional` | Governed repair entry and review flow are protected. Scheduler-coordinated injection/replay continuation remains compatibility-sensitive and must stay internal. |
| rollback | `freeze_protected`, `internal_only` | Rollback execution is runtime-owned. Code Chain patch restore is isolated behind the runtime helper and must preserve result shape/reason strings. |
| governed mutation | `freeze_protected` | Gateway behavior is a stable contract candidate. Mutation pipeline, patch apply, approval, sandbox, verification, rollback, and evidence internals remain internal. |
| recovery | `internal_only`, `transitional` | Recovery execution remains internal. No public recovery API should be declared until governed wrapper and dedicated regression coverage exist. |
| replay | `freeze_protected`, `internal_only` | Read-only replay/reporting is contract-candidate material. Scheduler retry/repair replay continuation remains internal and idempotency-sensitive. |
| evidence | `freeze_protected`, `internal_only` | Read/query evidence surfaces may stabilize. Evidence emitters/adapters and persistence ownership remain internal and boot/runtime owned. |
| scheduler facade | `freeze_protected`, `compatibility_sensitive` | `ZeroSystem` and scheduler public lifecycle behavior are protected. `scheduler.py` internals and compatibility bindings must not become public API. |
| agent runtime request | `freeze_protected` | Agent loop is request-only for runtime mutation authority. It must not directly own rollback, mutation, recovery, patch, or override execution. |

## 3. Runtime Ownership Verdict

- `scheduler.py` is not public API.
- `scheduler_core` helpers are internal and must not be imported by external-facing layers.
- Actual enqueue primitive execution remains scheduler-owned.
- Compatibility monkey-patch bindings remain scheduler-owned and compatibility-sensitive.
- `agent_loop` does not own rollback authority.
- Code Chain patch restore is owned by `core.runtime.code_chain_patch_restore.request_code_chain_patch_restore`.
- External-facing layers are guarded by `tests/test_runtime_boundary_imports.py`.
- External-facing layers are guarded by `tests/test_runtime_mutation_authority_boundaries.py`.
- `services/system_boot.py` remains the only explicit bootstrap exception for direct scheduler import.

Ownership verdict: current ownership boundaries are sufficient for Freeze Candidate Baseline.

## 4. Required Protected Smoke Pack

These exact tests must pass before future runtime-kernel changes are considered safe:

```text
python -m pytest tests/test_runtime_boundary_imports.py -q
python -m pytest tests/test_runtime_mutation_authority_boundaries.py -q
python -m pytest tests/test_repair_chain_runtime.py -q
python -m pytest tests/test_scheduler_parser_helpers.py -q
```

If `python` is not on PATH, use the known passing bundled Python executable for this workspace.

## 5. Remaining Blockers

No real blockers are currently identified.

The following are not blockers for Freeze Candidate Baseline:

- existing `datetime.utcnow()` deprecation warnings;
- absence of implemented public runtime API wrappers;
- recovery facade not yet implemented;
- compatibility legacy surfaces still existing;
- future authority annotations not yet implemented;
- future HTTP/RPC/CLI/UI mapping not yet implemented.

## 6. Freeze Declaration Criteria

Declare `Runtime Kernel Freeze Candidate Baseline` only when all of the following are true:

- this review document exists and records verdict `freeze_candidate`;
- `docs/runtime_kernel_boundary_contract.md` remains the Runtime Kernel boundary SSOT;
- `docs/runtime_mainline_freeze_audit.md` classifies protected runtime flows;
- `docs/runtime_freeze_guardrails.md` defines protected tests, sensitive modules, change rules, scheduler rules, and self-edit rules;
- `docs/runtime_freeze_candidate_validation.md` validates boundary and authority enforcement;
- `docs/runtime_freeze_hardening_plan.md` defines hardening rules and compatibility expectations;
- `tests/test_runtime_boundary_imports.py` passes;
- `tests/test_runtime_mutation_authority_boundaries.py` passes;
- `tests/test_repair_chain_runtime.py` passes;
- `tests/test_scheduler_parser_helpers.py` passes;
- no external-facing layer directly imports protected scheduler/runtime internals;
- no external-facing layer directly calls obvious rollback, mutation, recovery, patch apply, approval, repair transaction, override, bypass, or unsafe apply authority;
- scheduler remains isolated from public API expansion;
- agent loop remains request-only for runtime authority;
- Code Chain patch restore remains runtime-owned;
- no runtime behavior change, scheduler refactor, file move, runtime API implementation, broad cleanup, or warning cleanup is bundled into the declaration.

## 7. Next Phase Recommendation

Recommendation: `declare_freeze_candidate_baseline`

The protected boundary tests exist, the authority radar exists, rollback authority has been isolated from `agent_loop`, the guardrail docs are in place, and the current protected smoke pack has been passing. The next phase should declare the Runtime Kernel Freeze Candidate Baseline, then require future runtime-kernel changes to satisfy the protected smoke pack and guardrail rules.

## 8. Non-Goals

This review does not:

- implement runtime APIs;
- implement wrappers;
- refactor `scheduler.py`;
- move files;
- change runtime behavior;
- clean `datetime.utcnow()` warnings;
- remove compatibility bindings;
- declare the Runtime Kernel permanently frozen.
