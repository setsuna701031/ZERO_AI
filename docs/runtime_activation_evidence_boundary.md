# Runtime Activation Evidence Boundary

Final decision: GO for evidence boundary definition only.

Runtime activation remains disabled.

## Purpose

This document defines the evidence boundary required before any future runtime activation authorization may be considered valid.

## Core Rule

Authorization without evidence is not valid authority.

Operator approval and activation authorization must both be backed by deterministic evidence before any future runtime activation may proceed.

## Evidence Requirements

- Activation request identity is required.
- Operator approval evidence is required.
- Authorization evidence is required.
- Authority lineage evidence is required.
- Evidence must be deterministic.
- Evidence must be auditable.
- Evidence must be scoped to one activation request.
- Evidence must not be fabricated by scheduler.
- Evidence must not be fabricated by executor.
- Evidence must not be reused by recovery.
- Stale evidence must not activate runtime.
- Missing evidence is NO-GO.
- Runtime mutation remains forbidden.

## Ownership

- Operator approval remains required.
- Authorization authority remains separate from approval.
- Evidence authority remains separate from scheduler and executor.
- Scheduler remains owner of scheduling only.
- Executor remains owner of execution only.
- Recovery remains disabled.
- Runtime mutation remains forbidden.

## Forbidden Behavior

This boundary does not create, connect, or enable:

- runtime activation
- recovery activation
- scheduler control
- executor control
- evidence stores
- evidence writers
- authorization tokens
- launchers
- start scripts
- CLI execution commands
- service connections
- runtime loops
- runtime mutation
