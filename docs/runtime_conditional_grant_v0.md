# Runtime Conditional Grant v0

Date: 2026-05-18

This document defines the minimum future conditions for the first `granted=True` execution grant. It is design-only: it does not implement `granted=True`, connect scheduler, enqueue work, execute work, or change runtime behavior.

## 1. Current Checkpoint

The current checkpoint consists of:

- Runtime Admission Governance v0.
- RuntimeExecutionGrant v0.
- RuntimeGrantIssuer v0.

The current implementation remains default-deny:

- `RuntimeExecutionGrant.granted` remains `False`.
- `RuntimeGrantIssuer.issue_grant()` returns `status="grant_not_issued"`.
- `RuntimeGrantIssuer.issue_grant()` returns `granted_by="runtime_grant_issuer_v0"`.
- `RuntimeOwnershipDecision.accepted` remains `False`.
- `RuntimeExecutionLease.granted` remains `False`.
- Public `submit_runtime_task()` still returns `accepted_not_connected`.

## 2. Conditional Grant Minimum Principles

The first future `granted=True` path must satisfy these minimum principles:

- Only `RuntimeGrantIssuer` may produce `granted=True`.
- `policy.allowed=True` is necessary but not sufficient.
- `lease.granted=True` is required.
- `authority_scope` must not be `none`.
- `risk_level` must be within an explicitly allowed range.
- Trace, lease, and grant lineage must be complete.
- `granted=True` still does not mean the request has been enqueued or executed.

Required lineage:

```text
request_id == lease.request_id
trace_id == admission_trace.trace_id
lease_id == lease.lease_id
admission_trace.grant_id == grant.grant_id
```

The grant is authority to consider handoff only. It is not queue mutation, scheduler access, execution, mutation, recovery, or replay.

## 3. First Allowed Scope Draft

The first candidate scopes for future conditional grants are:

- `dry_run`
- `read_only`

These scopes are candidates only. They still require explicit eligibility checks and do not imply scheduler handoff.

Temporarily forbidden scopes:

- `write`
- `mutation`
- `recovery`
- `replay`
- `scheduler_enqueue`

## 4. Explicit Prohibitions

The conditional grant design explicitly forbids:

- `submit_runtime_task()` automatically executing because the request was accepted.
- Connector directly enqueueing.
- Ownership gate directly producing grants.
- Grant issuer directly calling scheduler.
- `granted=True` directly meaning scheduler handoff.
- Bypassing Execution Bridge or Scheduler Adapter.

These prohibitions apply even after a future conditional grant path exists.

## 5. Next Code Contract

The next code contract is expected to introduce:

- `RuntimeGrantEligibility`.
- `RuntimeGrantIssuer.evaluate_eligibility()`.
- `RuntimeGrantIssuer.issue_grant()` checking eligibility before issuing any grant.

The v0 code must remain default-deny unless an explicit test mode permits a `dry_run` grant. Any such mode must be isolated, auditable, and unable to reach scheduler, enqueue, execution, mutation, recovery, or replay.

## 6. Acceptance Criteria

This design checkpoint is accepted only if:

- Changes are docs-only.
- Governance and boundary tests remain passing.
- Repair and scheduler regression tests remain passing.
- `git status` contains only `docs/runtime_conditional_grant_v0.md` and `docs/devlog.md`.

Required validation commands:

```text
python -m pytest tests/test_runtime_grant_issuer_contract.py tests/test_runtime_execution_grant_contract.py tests/test_runtime_admission_trace_contract.py tests/test_runtime_execution_lease_contract.py tests/test_runtime_ownership_gate_contract.py tests/test_runtime_connector_contract.py tests/test_runtime_public_surface_contract.py tests/test_runtime_boundary_imports.py tests/test_runtime_mutation_authority_boundaries.py -q

python -m pytest tests/test_repair_chain_runtime.py tests/test_scheduler_parser_helpers.py -q
```
