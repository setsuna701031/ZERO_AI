# Runtime Executor Admission Contract v1

Final decision: GO for contract definition only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This contract seals the boundary after scheduler dispatch authorization but before executor execution.

Current sealed chain:

ACTIVE -> runtime owner -> execution handoff -> scheduler admission -> dispatch authorization -> executor admission required -> execution still disabled

## Core Rule

Dispatch authorization != execution permission.

Executor admission required before any future executor execution.

## Executor Admission Rules

- Dispatch authorization is not execution permission.
- Executor admission required.
- Scheduler cannot call executor directly.
- Scheduler is not executor owner.
- Executor cannot self admit.
- Handoff chain evidence required.
- Executor must verify handoff chain.
- Dispatch authorization required.
- Executor must verify dispatch authorization.
- Dispatch evidence required.
- Executor must verify dispatch evidence.
- Executor admission decision required.
- Executor admission audit required.
- Recovery cannot call executor.
- Missing executor admission cannot execute.
- No executor path created.
- Mutation disabled.

## Forbidden Behavior

- dispatch authorization -> executor.run()
- scheduler direct executor call
- executor self-admission
- executor execution from dispatch authorization alone
- recovery direct executor call
- execution without handoff chain evidence
- execution without dispatch evidence
- silent executor admission without audit
- executor admission runtime code
- executor bridge
- runtime mutation
