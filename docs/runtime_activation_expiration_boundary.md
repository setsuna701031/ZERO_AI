# Runtime Activation Expiration Boundary

Final decision: GO for expiration boundary definition only.

Runtime activation remains disabled.

## Purpose

This document defines expiration requirements for any future runtime activation chain.

## Core Rule

Activation authority must become invalid after expiration.

## Expiration Requirements

- Activation expiration is required.
- Operator approval expiration is required.
- Authorization expiration is required.
- Evidence expiration is required.
- Lineage expiration is required.
- Expired activation must not execute.
- Expired approval must not authorize activation.
- Expired authorization must not grant execution authority.
- Expired evidence must not validate activation.
- Expired lineage must not preserve authority.
- Recovery must not restore expired authority.
- Scheduler must not ignore expiration.
- Executor must not ignore expiration.
- Runtime mutation remains forbidden.

## Ownership

- Expiration authority remains separate.
- Scheduler remains owner of scheduling only.
- Executor remains owner of execution only.
- Recovery remains disabled.

## Forbidden Behavior

This boundary does not create:

- runtime activation
- recovery activation
- expiration stores
- expiration validators
- scheduler control
- executor control
- launchers
- start scripts
- CLI execution commands
- service connections
- runtime loops
- runtime mutation
