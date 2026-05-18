# Runtime Freeze Hardening Plan - Phase 4-H

Date: 2026-05-18

Source documents and enforcement tests:

- `docs/runtime_kernel_boundary_contract.md`
- `docs/runtime_freeze_guardrails.md`
- `docs/runtime_freeze_candidate_validation.md`
- `tests/test_runtime_boundary_imports.py`
- `tests/test_runtime_mutation_authority_boundaries.py`

This plan hardens the current Runtime Governance Checkpoint into a stricter Runtime Kernel Freeze Candidate. It does not implement APIs, expand features, refactor `scheduler.py`, move files, change runtime behavior, or clean existing warnings.

## Current Freeze Status

Status: `freeze_candidate`

Rationale:

- Runtime boundary contract exists and defines public, internal mutation, and compatibility legacy surfaces.
- Freeze guardrails define protected flows, sensitive modules, change rules, scheduler rules, and self-edit rules.
- Freeze candidate validation confirms boundary and authority enforcement are active.
- Protected smoke pack has passed in the current Phase 4 series.
- No real blocker is currently identified for freeze-candidate status.

This is not `frozen`: public runtime APIs are not implemented, recovery remains internal/transitional, and compatibility surfaces still exist.

## 1. Freeze-Critical Runtime Paths

| Path | Owning layer | Freeze-critical behavior | Hardening stance |
| --- | --- | --- | --- |
| Repair | `repair_runtime` with scheduler coordination | Governed repair entry, transaction state, review/approval, injected-step persistence, replay continuation, scheduler-owned enqueue after injection | Do not change semantics without protected smoke pack and rollback plan. Do not expose internals. |
| Rollback | `mutation_runtime` / `repair_runtime`; Code Chain restore in runtime | Runtime-owned rollback execution, Code Chain restore request wrapper, rollback result normalization | Keep external layers request-only. Preserve return and error shapes. |
| Governed mutation | `mutation_runtime` | Gateway request normalization, policy/guard, approval, sandbox, patch apply, rollback, verification, evidence | Gateway is a stable contract candidate; pipeline internals remain internal. |
| Recovery | `recovery_runtime` | Recovery policy, dry-run, commit gate, approval, rollback, evidence | Internal/transitional. No public exposure without explicit review and dedicated tests. |
| Replay | read-only runtime/tasks reporting; scheduler internal for retry/repair continuation | Read-only replay snapshots/narratives/events; idempotent retry/repair continuation metadata | Read-only surface may stabilize. Continuation helpers remain internal. |
| Evidence | boot-owned wiring; scheduler/runtime/executor adapters | Evidence provenance, event ordering, trace persistence, audit artifact shape, adapter ownership | Read/query surface may stabilize. Direct evidence emission remains internal. |
| Scheduler facade | `scheduler_facade` over `scheduler_internal` | `ZeroSystem` health/tick/run-until-idle/queue views; scheduler public lifecycle; scheduler-owned enqueue primitive | Do not expand `scheduler.py` as public API. Keep external imports blocked. |
| Agent runtime request | `agent_loop` request-only; runtime/tasks execute authority | Agent may request scheduler/runtime work; no direct rollback, mutation, recovery, patch, or override authority | Preserve request-only semantics and self-edit guardrails. |

## 2. Hardening Rules

### Must Not Change

These must not change during freeze hardening unless the change is explicitly scoped, reviewed, and backed by regression evidence:

- scheduler compatibility binding order;
- scheduler private queue, retry, replay, repair, persistence, dispatch/finalize, worker release, and enqueue semantics;
- repair transaction lifecycle states and transition rules;
- repair review approval/rejection meaning;
- repair injection idempotency and injected-step persistence coordination;
- replay continuation metadata and idempotent replay behavior;
- governed mutation request/result normalization;
- mutation approval, sandbox, patch apply, rollback, verification, and evidence sequencing;
- recovery policy, dry-run, commit gate, rollback, and evidence semantics;
- Code Chain patch restore return shape and reason strings;
- evidence IDs, audit refs, emitted event order, and read-only audit artifact shape;
- agent loop request-only boundary;
- boundary import and mutation authority tests.

### May Change With Protected Smoke Pack

These may change when narrowly scoped and followed by the protected smoke pack:

- documentation and contract wording;
- tests that strengthen boundary enforcement;
- internal helper extraction that preserves exact behavior;
- comments and ownership markers;
- read-only report formatting with stable payload fields preserved;
- small runtime-owned wrappers that remove authority from external layers without changing behavior.

### Requires Rollback Plan

A rollback plan is required before changing:

- `core/tasks/scheduler.py` executable logic;
- `core/tasks/scheduler_core/*`;
- actual enqueue primitive execution;
- task runtime state persistence writes;
- repair transaction commit/apply/injection execution;
- rollback execution helpers;
- mutation patch application or sandbox behavior;
- governed mutation gateway request/result packaging;
- recovery coordinator/policy/commit gate/execution behavior;
- evidence persistence, adapter wiring, or emitted record shape;
- agent self-edit mutation routing.

The rollback plan must state affected files, previous behavior, verification commands, and the exact revert path.

### Requires Explicit Review

Explicit review is required for any change that:

- exposes scheduler or `scheduler_core` as public API;
- adds new external imports of scheduler/runtime internals;
- weakens or removes boundary tests;
- allows agent, capability, planning, service, UI, plugin, or remote orchestration layers to call direct mutation authority;
- bypasses policy, guard, approval, rollback, verification, or evidence for mutating operations;
- makes recovery public;
- changes compatibility monkey-patch binding order;
- mixes warning cleanup or broad refactors with freeze-critical changes.

## 3. Compatibility Expectations

### Return Shape Stability

Freeze-critical entrypoints must preserve existing top-level result keys and status meanings unless a migration plan exists. This includes:

- repair transaction/review/apply payloads;
- governed mutation gateway results;
- Code Chain patch restore results;
- replay snapshot/narrative outputs;
- scheduler tick/run results;
- agent loop response envelopes;
- evidence/audit artifact builders.

### Error Shape Stability

Failure payloads must preserve:

- `ok` / success booleans where currently present;
- `status` fields where currently present;
- `reason` values and meanings for compatibility paths;
- `error` text presence and failure packaging;
- rollback and verification details when mutation fails;
- no silent conversion of failures into success.

### Authority Request Shape Stability

Authority request payloads must preserve:

- caller intent;
- task or runtime object identity;
- operation type;
- target paths/scope;
- approval/review references when required;
- rollback and verification requirements;
- evidence/audit references.

External layers may request authority but must not become authority owners.

### Evidence and Audit Shape Stability

Evidence and audit payloads must preserve:

- event ordering;
- runtime/task/step references;
- mutation/repair/recovery identifiers;
- approval ids when required;
- rollback ids or rollback result references when applicable;
- verification ids/results;
- final status;
- replay/audit refs.

Direct evidence emission from external layers remains forbidden.

## 4. Protected Smoke Pack

The protected smoke pack is mandatory for freeze-critical runtime changes:

```text
python -m pytest tests/test_runtime_boundary_imports.py -q
python -m pytest tests/test_runtime_mutation_authority_boundaries.py -q
python -m pytest tests/test_repair_chain_runtime.py -q
python -m pytest tests/test_scheduler_parser_helpers.py -q
```

Protected tests:

- `tests/test_runtime_boundary_imports.py`
- `tests/test_runtime_mutation_authority_boundaries.py`
- `tests/test_repair_chain_runtime.py`
- `tests/test_scheduler_parser_helpers.py`

Known `datetime.utcnow()` deprecation warnings in `core/runtime/mutation_boundary.py` do not block this pack and must not be cleaned as part of freeze hardening.

## 5. Freeze Blocker Checklist

Real blockers for Runtime Kernel Freeze Candidate status:

- protected smoke pack failure;
- external-facing layer can import scheduler/runtime mutation internals without test failure;
- external-facing layer can directly call obvious mutation, rollback, recovery, patch apply, approval, repair transaction, override, bypass, or unsafe apply authority without test failure;
- agent loop regains direct rollback/mutation execution authority;
- scheduler internals are expanded as public API;
- repair or mutation result/error shapes change without migration plan;
- recovery execution is made public without governed wrapper, explicit review, and dedicated tests;
- evidence write ownership can be bypassed by external layers;
- compatibility monkey-patch binding order changes without targeted regression coverage;
- runtime behavior changes are mixed with broad cleanup or warning cleanup.

Not blockers:

- existing `datetime.utcnow()` warnings;
- absence of a new public runtime API implementation;
- future cleanup of legacy compatibility modules;
- future authority annotations;
- future HTTP/RPC/CLI/UI endpoint design;
- broader recovery-specific tests, provided recovery remains internal.

## 6. Runtime Freeze Candidate Declaration

Current status remains: `freeze_candidate`

Declaration statement:

ZERO Runtime Kernel may be treated as a Freeze Candidate while the protected smoke pack passes and the boundary/authority tests remain active. The candidate state freezes the current ownership rules and guards against drift; it does not freeze a final public runtime API.

Before any formal candidate declaration, confirm:

- this hardening plan exists;
- boundary contract, guardrails, and validation docs remain current;
- protected smoke pack passes;
- no real blocker from the checklist is present;
- no scheduler refactor, file move, behavior change, runtime API implementation, or warning cleanup is bundled into the declaration.

## 7. Non-Goals

This hardening plan does not:

- implement runtime APIs;
- implement wrappers;
- refactor `scheduler.py`;
- move files;
- change runtime behavior;
- clean `datetime.utcnow()` warnings;
- add features;
- remove compatibility bindings;
- declare the Runtime Kernel permanently frozen.
