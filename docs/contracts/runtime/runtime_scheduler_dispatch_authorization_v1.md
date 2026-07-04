# Runtime Scheduler Dispatch Authorization Contract v1

Final decision: GO for contract definition only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This contract seals the boundary after scheduler admission but before dispatch.

Current sealed chain:

ACTIVE -> runtime owner -> execution handoff -> scheduler admission -> dispatch authorization required -> scheduler dispatch still disabled

## Core Rule

Scheduler admission != dispatch permission.

Dispatch authorization required before any future scheduler dispatch.

## Dispatch Authorization Rules

- Scheduler admission is not dispatch permission.
- Dispatch authorization required.
- Scheduler cannot self authorize dispatch.
- Scheduler cannot dispatch from admission alone.
- Owner-approved handoff required.
- Dispatch authorization requires owner-approved handoff.
- Dispatch evidence required.
- Dispatch audit required.
- Executor remains unavailable.
- Recovery cannot issue dispatch authorization.
- Rejected or missing dispatch authorization cannot execute.
- Missing dispatch authorization cannot execute.
- No dispatch path created.
- Mutation disabled.

## Forbidden Behavior

- admitted handoff -> dispatch
- scheduler self-dispatch
- scheduler self-authorization
- recovery-issued dispatch authorization
- dispatch without evidence
- dispatch without audit
- executor execution from admission alone
- scheduler dispatch code
- executor bridge
- runtime mutation
