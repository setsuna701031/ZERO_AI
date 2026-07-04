# Runtime Activation Lineage Boundary

Final decision: GO for lineage boundary definition only.

Runtime activation remains disabled.

## Purpose

This document defines the lineage boundary required before any future runtime activation chain may execute.

## Core Rule

Activation authority requires complete lineage continuity.

Approval, authorization, and evidence must all belong to the same activation request lineage.

## Lineage Requirements

- Activation request lineage is required.
- Operator approval lineage is required.
- Authorization lineage is required.
- Evidence lineage is required.
- Lineage continuity is required.
- Lineage must be deterministic.
- Lineage must be auditable.
- Lineage must not be fabricated by scheduler.
- Lineage must not be fabricated by executor.
- Recovery must not reuse previous activation lineage.
- Broken lineage is NO-GO.
- Cross-request lineage reuse is NO-GO.
- Runtime mutation remains forbidden.

## Ownership

- Operator approval remains required.
- Authorization authority remains separate.
- Evidence authority remains separate.
- Lineage authority remains separate from scheduler and executor.
- Scheduler remains owner of scheduling only.
- Executor remains owner of execution only.
- Recovery remains disabled.

## Forbidden Behavior

This boundary does not create:

- runtime activation
- recovery activation
- lineage stores
- lineage writers
- scheduler control
- executor control
- launchers
- start scripts
- CLI execution commands
- service connections
- runtime loops
- runtime mutation
