# Runtime Activation Scheduler Admission Contract v1

Final decision: GO for contract definition only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This contract seals scheduler admission after an execution handoff exists.

Boundary:

handoff -> scheduler admission check -> accepted / rejected decision

## Core Rule

Execution handoff required before scheduler admission.

ACTIVE is not scheduler admission permission.

## Admission Rules

- Scheduler admission requires execution handoff.
- ACTIVE != scheduler admission.
- Scheduler cannot create handoff.
- Scheduler cannot approve owner decision.
- Scheduler cannot self authorize.
- Scheduler cannot dispatch from ACTIVE alone.
- Owner approval required before scheduler admission.
- Handoff evidence required before scheduler admission.
- Admission audit required for accepted and rejected decisions.
- Recovery cannot create or inject handoff.
- Rejected admission cannot execute.
- No dispatch path created.
- Mutation disabled.

## Required Admission Inputs

- execution handoff
- owner approval
- handoff evidence
- admission audit reference

## Forbidden Behavior

- ACTIVE -> scheduler dispatch
- scheduler self-authorization
- recovery-created handoff admission
- recovery-injected handoff admission
- silent admission without audit
- rejected admission execution
- scheduler runtime admission code
- runtime mutation
