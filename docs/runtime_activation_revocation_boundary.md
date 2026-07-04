# Runtime Activation Revocation Boundary

Final decision: GO for revocation boundary definition only.

Runtime activation remains disabled.

## Purpose

This document defines revocation requirements for any future runtime activation chain.

## Core Rule

Previously valid activation authority must become invalid when revoked.

## Revocation Requirements

- Operator approval revocation is required.
- Authorization revocation is required.
- Evidence revocation is required.
- Lineage revocation is required.
- Revoked activation must not execute.
- Revoked approval must not authorize activation.
- Revoked authorization must not grant execution authority.
- Revoked evidence must not validate activation.
- Revoked lineage must not preserve authority.
- Recovery must not restore revoked authority.
- Scheduler must not ignore revocation.
- Executor must not ignore revocation.
- Runtime mutation remains forbidden.

## Ownership

- Revocation authority remains separate.
- Scheduler remains owner of scheduling only.
- Executor remains owner of execution only.
- Recovery remains disabled.

## Forbidden Behavior

This boundary does not create:

- runtime activation
- recovery activation
- revocation stores
- revocation validators
- scheduler control
- executor control
- launchers
- start scripts
- CLI execution commands
- service connections
- runtime loops
- runtime mutation
