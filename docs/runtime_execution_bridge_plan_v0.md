# Runtime Execution Bridge Plan v0

Date: 2026-05-18

This plan defines how an execution bridge should be introduced after Runtime Admission Governance v0. It is design-only: no execution capability, scheduler wiring, queue access, mutation, recovery, replay behavior, or scheduler refactor is added by this plan.

## 1. Current Frozen Baseline

Runtime Admission Governance v0 is frozen as:

```text
Public Surface
-> Connector
-> Ownership Gate
-> Admission Policy
-> Admission Trace
-> Execution Lease
```

Current posture:

- default-deny;
- `RuntimeAdmissionPolicyDecision.allowed=False`;
- `RuntimeOwnershipDecision.accepted=False`;
- `RuntimeExecutionLease.granted=False`;
- `RuntimeAdmissionTrace.decision="denied"`;
- public `submit_runtime_task()` returns `accepted_not_connected`;
- no scheduler, executor, mutation, recovery, or replay coupling in public surface / connector / gate / policy / trace / lease.

## 2. Next Bridge Goal

The next stage is to define a controlled execution handoff after the default-deny governance path.

The bridge must not turn admission into execution by itself. It should receive a governance result, inspect the execution lease, and only hand off to scheduler-facing code when a future policy-controlled lease is explicitly granted.

## 3. Explicit Prohibitions

The execution bridge work must not:

- let `submit_runtime_task()` call scheduler directly;
- put execution logic in `RuntimeConnector`;
- put scheduler logic in `RuntimeOwnershipGate`;
- bypass policy, admission trace, or execution lease;
- add mutation behavior;
- add recovery behavior;
- add replay behavior;
- enqueue without a granted lease;
- make scheduler internals public API;
- import `scheduler.py` from public surface, connector, ownership gate, admission policy, admission trace, or execution lease.

## 4. Planned Bridge Structure

Target structure:

```text
Public Surface
-> Connector
-> Ownership Gate
-> Policy
-> Trace
-> Lease
-> Execution Bridge
-> Scheduler Adapter
```

Responsibilities:

- Public Surface exposes stable external entrypoints only.
- Connector builds and forwards request envelopes only.
- Ownership Gate composes policy, trace, lease, and decision only.
- Policy decides whether admission may proceed.
- Trace records admission lineage.
- Lease records whether execution ownership is granted.
- Execution Bridge evaluates whether a granted lease exists and creates a handoff record.
- Scheduler Adapter is the only future layer allowed to touch scheduler-facing behavior.

## 5. Contracts To Design First

Before adding any execution handoff behavior, define contract-only modules for:

### RuntimeExecutionBridge

Purpose:

- accept an ownership decision and request envelope;
- reject handoff when `lease.granted` is false;
- never import scheduler directly;
- never enqueue directly.

### RuntimeSchedulerAdapter

Purpose:

- become the only scheduler-facing bridge point;
- keep scheduler coupling out of public surface, connector, gate, policy, trace, lease, and bridge contracts;
- preserve scheduler ownership of actual enqueue primitive execution.

### RuntimeExecutionGrant

Purpose:

- represent future explicit permission to hand off execution;
- include request id, lease id, trace id, grant status, authority scope, and policy reference;
- remain absent or not granted in v0 default-deny mode.

### RuntimeExecutionHandoffRecord

Purpose:

- record attempted handoff lineage;
- include request id, trace id, lease id, policy rule, bridge decision, adapter target, and status;
- record rejection when no granted lease exists.

## 6. Phase 1 Bridge Behavior

The first execution bridge phase remains default-deny:

- bridge may exist as a contract;
- bridge must reject handoff without a granted lease;
- bridge must not call scheduler;
- bridge must not enqueue;
- bridge must not execute;
- bridge must return a stable rejected/not-connected handoff record;
- public `submit_runtime_task()` behavior remains unchanged until a later explicit wiring phase.

## 7. Acceptance Criteria

Before any bridge implementation can be considered safe:

- governance tests remain `36 passed`;
- regression tests remain `80 passed`;
- no scheduler coupling appears in public surface, connector, gate, policy, trace, or lease;
- scheduler is reachable only through a future scheduler adapter;
- no enqueue happens before a real execution grant exists;
- mutation, recovery, and replay behavior remain untouched;
- boundary and authority tests remain green.

Required validation commands:

```text
python -m pytest tests/test_runtime_admission_policy_contract.py tests/test_runtime_admission_trace_contract.py tests/test_runtime_execution_lease_contract.py tests/test_runtime_ownership_gate_contract.py tests/test_runtime_connector_contract.py tests/test_runtime_public_surface_contract.py tests/test_runtime_boundary_imports.py tests/test_runtime_mutation_authority_boundaries.py -q

python -m pytest tests/test_repair_chain_runtime.py tests/test_scheduler_parser_helpers.py -q
```

## 8. Non-Goals

This plan does not:

- implement `RuntimeExecutionBridge`;
- implement `RuntimeSchedulerAdapter`;
- implement `RuntimeExecutionGrant`;
- implement `RuntimeExecutionHandoffRecord`;
- wire scheduler;
- enqueue tasks;
- execute tasks;
- change `scheduler.py`;
- change runtime behavior;
- add mutation, recovery, or replay behavior.
