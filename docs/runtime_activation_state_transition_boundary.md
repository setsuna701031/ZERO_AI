# Runtime Activation State Transition Boundary

Final decision: GO for state transition boundary definition only.

Runtime activation remains disabled.

## Purpose

This document defines legal state transition requirements for any future runtime activation lifecycle.

## Core Rule

Runtime activation state must not jump directly from disabled to active.

## Required State Order

A future activation lifecycle must preserve this order:

- DISABLED
- REQUESTED
- APPROVED
- AUTHORIZED
- EVIDENCE_VERIFIED
- LINEAGE_VERIFIED
- REPLAY_CHECKED
- LIFETIME_CHECKED
- AUDITED
- COMMITTED
- ACTIVE

## Transition Requirements

- Activation state transition validation is required.
- Illegal transition is forbidden.
- Skipped activation state is forbidden.
- Transition evidence is required.
- Transition audit is required.
- Transition lineage is required.
- Scheduler must not force activation transition.
- Executor must not force activation transition.
- Recovery must not jump activation state.
- Runtime mutation remains forbidden.

## Ownership

- State transition authority remains separate.
- Scheduler remains owner of scheduling only.
- Executor remains owner of execution only.
- Recovery remains disabled.

## Forbidden Behavior

This boundary does not create:

- runtime activation
- recovery activation
- state transition stores
- state transition writers
- scheduler control
- executor control
- launchers
- start scripts
- CLI execution commands
- service connections
- runtime loops
- runtime mutation
