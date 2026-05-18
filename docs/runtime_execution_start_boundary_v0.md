# Runtime Execution Start Boundary v0

Date: 2026-05-18

This document defines the minimum future conditions for the first controlled path that may set `executed=True`. It is documentation-only: it does not implement execution, change executor, change scheduler, run tasks, or connect mutation, recovery, or replay.

## 1. Current Remote Checkpoint

The current remote checkpoint is:

- Runtime Execution Lifecycle Skeleton has been pushed to GitHub.
- `execution_pending=True` is allowed.
- `executed=False` remains required.

## 2. Stable Chain

Current stable chain:

```text
Public Surface
-> Connector
-> Ownership Gate
-> Admission Policy
-> Admission Trace
-> Execution Lease
-> Grant Eligibility
-> Grant Issuer
-> Execution Grant
-> Execution Bridge
-> Scheduler Adapter
-> Queue Admission
-> Controlled Enqueue
-> Execution Token
-> Execution Pending
```

This chain can represent pending execution authority, but it still does not execute work.

## 3. Core Boundaries

The current boundaries remain:

- `execution_pending=True` does not mean `executed=True`.
- `enqueued=True` does not mean `executed=True`.
- `scheduler_touched=True` does not mean `executed=True`.
- `grant_issued` does not mean `executed=True`.
- `submit_runtime_task` accepted does not mean `executed=True`.

Execution start must be a separate, explicit, auditable transition.

## 4. Minimum Conditions For First `executed=True`

The first future `executed=True` path may only be considered when all of these conditions are satisfied:

- `execution_pending=True`.
- `execution_token.revoked=False`.
- Controlled enqueue accepted.
- Queue admission accepted.
- `grant.granted=True`.
- `authority_scope` is `dry_run` or `read_only`.
- `risk_level` is `low`.
- Lineage is complete for `request_id`, `trace_id`, `lease_id`, `grant_id`, `queue_admission_id`, `enqueue_id`, and `execution_token_id`.
- An execution start record must be produced.
- `executed=True` can only be produced by Execution Start Controller.

These are necessary conditions only. They do not authorize real task execution in v0.

## 5. Version 0 Forbidden Scope

Version 0 forbids:

- `write`.
- `mutation`.
- `recovery`.
- `replay`.
- `scheduler_enqueue`.
- Public surface directly executing.
- Connector, ownership gate, execution bridge, or scheduler adapter directly executing.
- Executor import.
- Real task execution.
- Mutation, recovery, or replay side effects.

## 6. Next Code Contract

The next code contract is expected to define:

- `RuntimeExecutionStartRequest`.
- `RuntimeExecutionStartDecision`.
- `RuntimeExecutionStartController`.

Required semantics:

- First-version `executed=True` can only mean a non-executing `dry_run` / `read_only` lifecycle marker.
- It must not run a real task.
- It must not call executor.
- It must not call scheduler.
- `executed=True` must remain auditable, revocable, and traceable.

## 7. Acceptance Criteria

This checkpoint is accepted only if:

- Changes are docs-only.
- Governance, routing, and lifecycle tests remain passing.
- Repair and scheduler regression tests remain passing.
- `git status` contains only `docs/runtime_execution_start_boundary_v0.md` and `docs/devlog.md`.
- No runtime code changed.

Required validation commands:

```text
python -m pytest tests/test_runtime_execution_pending_contract.py tests/test_runtime_execution_token_contract.py tests/test_runtime_controlled_enqueue_contract.py tests/test_runtime_queue_admission_contract.py tests/test_runtime_scheduler_adapter_contract.py tests/test_runtime_execution_handoff_contract.py tests/test_runtime_execution_bridge_contract.py tests/test_runtime_grant_issuer_contract.py tests/test_runtime_execution_grant_contract.py tests/test_runtime_grant_eligibility_contract.py tests/test_runtime_admission_trace_contract.py tests/test_runtime_execution_lease_contract.py tests/test_runtime_ownership_gate_contract.py tests/test_runtime_connector_contract.py tests/test_runtime_public_surface_contract.py tests/test_runtime_boundary_imports.py tests/test_runtime_mutation_authority_boundaries.py -q

python -m pytest tests/test_repair_chain_runtime.py tests/test_scheduler_parser_helpers.py -q
```
