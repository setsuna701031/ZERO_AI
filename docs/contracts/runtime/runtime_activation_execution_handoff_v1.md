# Runtime Activation Execution Handoff Contract v1

Final decision: GO for contract definition only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This contract seals the boundary between ACTIVE state, runtime owner, scheduler, and executor.

## Core Rule

ACTIVE is not execution permission.

A runtime becoming ACTIVE does not authorize scheduling or execution. Execution requires a separate execution handoff object approved by the runtime owner.

## Authority Rules

- Runtime owner owns the activation decision.
- Scheduler cannot infer execution permission from ACTIVE state.
- Executor cannot accept activation directly.
- Executor cannot execute from ACTIVE state alone.
- Execution requires handoff object.
- Execution handoff required before scheduler dispatch.
- Runtime owner must be separate from executor.
- Scheduler requires handoff before scheduling execution.
- Executor requires handoff before accepting work.
- Recovery cannot create handoff.
- Runtime mutation remains disabled.

## Handoff Object Required Fields

Every execution handoff object must include:

- `activation_id`
- `runtime_owner_id`
- `handoff_id`
- `handoff_state`
- `execution_permission`
- `evidence_reference`
- `audit_reference`

## Field Defaults

- `execution_permission` default: `false`

## Forbidden Behavior

This contract forbids:

- ACTIVE as execution permission
- scheduler active-only trigger
- scheduler self authorization
- executor direct activation acceptance
- executor execution without handoff
- recovery handoff creation
- silent ACTIVE -> execute
- runtime mutation
