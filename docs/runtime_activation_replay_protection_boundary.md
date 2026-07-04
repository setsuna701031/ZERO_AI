# Runtime Activation Replay Protection Boundary

Final decision: GO for replay protection boundary definition only.

Runtime activation remains disabled.

## Purpose

This document defines replay protection requirements for any future runtime activation chain.

## Core Rule

A previous valid activation chain must never become future execution authority.

## Replay Protection Requirements

- Activation request replay is forbidden.
- Operator approval replay is forbidden.
- Authorization replay is forbidden.
- Evidence replay is forbidden.
- Lineage replay is forbidden.
- Stale activation chains are forbidden.
- Expired activation authority is invalid.
- Replay detection is required before activation.
- Recovery must not replay activation authority.
- Scheduler must not replay activation authority.
- Executor must not replay activation authority.
- Runtime mutation remains forbidden.

## Ownership

- Replay protection authority remains separate.
- Scheduler remains owner of scheduling only.
- Executor remains owner of execution only.
- Recovery remains disabled.

## Forbidden Behavior

This boundary does not create:

- runtime activation
- recovery activation
- replay stores
- replay validators
- scheduler control
- executor control
- launchers
- start scripts
- CLI execution commands
- service connections
- runtime loops
- runtime mutation
