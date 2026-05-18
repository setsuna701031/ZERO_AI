# Runtime Execution Grant Model v0

Date: 2026-05-18

This document defines the conditions and boundaries for a future granted execution lease. It is documentation-only and does not add execution capability, scheduler wiring, runtime code, queue access, mutation, recovery, or replay behavior.

## 1. Current Status

The current runtime admission baseline is:

- Runtime Admission Governance v0 is frozen.
- Execution Bridge Plan v0 is established.
- Runtime execution leases are never granted; `RuntimeExecutionLease.granted` remains `False`.
- Public `submit_runtime_task()` still returns `accepted_not_connected`.

Current flow remains:

```text
Public Surface
-> Connector
-> Ownership Gate
-> Admission Policy
-> Admission Trace
-> Execution Lease
```

No runtime path is connected to scheduler handoff, enqueue, execution, mutation, recovery, or replay.

## 2. Execution Grant Core Principles

Execution grant semantics must preserve these boundaries:

- A request being accepted does not mean execution is granted.
- A policy decision being allowed does not mean the request has been enqueued.
- A granted lease only means the request may be handed off; it does not mean the request has executed.
- Scheduler handoff must go through Execution Bridge plus Scheduler Adapter.
- Every grant must be traceable, auditable, and revocable.

This separation keeps admission, permission, handoff, and actual scheduler execution as distinct stages.

## 3. RuntimeExecutionGrant Contract Draft

`RuntimeExecutionGrant` is a future contract for explicit handoff permission.

Draft fields:

```text
grant_id
request_id
trace_id
lease_id
granted: bool
status
reason
authority_scope
risk_level
granted_by
expires_at
metadata
```

Field intent:

- `grant_id`: stable identifier for the grant decision.
- `request_id`: request lineage from public surface / connector.
- `trace_id`: admission trace lineage for audit.
- `lease_id`: execution lease associated with the grant decision.
- `granted`: explicit boolean grant result.
- `status`: lifecycle status for the grant decision.
- `reason`: human-readable or machine-readable explanation.
- `authority_scope`: bounded permission scope covered by this grant.
- `risk_level`: assessed risk level for the handoff.
- `granted_by`: authority or component that produced the grant.
- `expires_at`: time after which the grant is invalid.
- `metadata`: structured extension data for audit and diagnostics.

## 4. Version 0 Default-Deny Boundary

Version 0 remains default-deny:

- Do not create real `granted=True` grants.
- Do not enqueue.
- Do not execute.
- Do not connect scheduler.
- Do not connect mutation, recovery, or replay.

Any grant record discussed in v0 is contract planning only. It must not change runtime behavior.

## 5. Future Requirements For `granted=True`

A future `granted=True` state is only eligible when all of these conditions are satisfied:

- `policy.allowed=True`.
- `lease.granted=True`.
- The trace decision is reproducible and auditable.
- `authority_scope` is explicit.
- `risk_level` is acceptable for the requested handoff.
- The Execution Bridge can reject or accept the handoff.
- The Scheduler Adapter is the only scheduler contact point.

These are necessary conditions, not automatic execution triggers. Even with a valid grant, enqueue must remain adapter-mediated and auditable.

## 6. Forbidden Paths

The following paths are explicitly forbidden:

- Public surface directly calls scheduler.
- Connector directly enqueues.
- Ownership gate directly executes.
- Policy directly mutates runtime state.
- Bridge bypasses lease.
- Adapter bypasses grant.
- `submit_runtime_task()` automatically executes because a request was accepted.

These prohibitions apply before and after a future grant contract exists.

## 7. Acceptance Criteria

This v0 document is accepted only if:

- Changes are docs-only.
- Governance and boundary tests still report `36 passed`.
- Regression tests still report `80 passed`.
- `git status` contains only `docs/runtime_execution_grant_model_v0.md` and `docs/devlog.md` for this work.
- No runtime code changed.

Required validation commands:

```text
python -m pytest tests/test_runtime_admission_policy_contract.py tests/test_runtime_admission_trace_contract.py tests/test_runtime_execution_lease_contract.py tests/test_runtime_ownership_gate_contract.py tests/test_runtime_connector_contract.py tests/test_runtime_public_surface_contract.py tests/test_runtime_boundary_imports.py tests/test_runtime_mutation_authority_boundaries.py -q

python -m pytest tests/test_repair_chain_runtime.py tests/test_scheduler_parser_helpers.py -q
```
