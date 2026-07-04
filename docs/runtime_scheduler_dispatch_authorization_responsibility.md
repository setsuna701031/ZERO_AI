# Runtime Scheduler Dispatch Authorization Responsibility Matrix

Final decision: GO for responsibility boundary only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This matrix defines responsibility after scheduler admission and before any future dispatch.

## Runtime Owner

- Owns activation decision.
- Owns handoff approval.
- Must provide owner-approved handoff before dispatch authorization.
- Must not execute.

## Scheduler

- May observe scheduler admission result.
- Must require dispatch authorization before dispatch.
- Must require owner-approved handoff.
- Must require dispatch evidence.
- Must require dispatch audit.
- Must not self authorize dispatch.
- Must not dispatch from admission alone.
- Must not self-dispatch.
- Must not create dispatch path.

## Executor

- Executor remains unavailable.
- Must not execute from admission alone.
- Must not execute rejected dispatch authorization.
- Must not execute missing dispatch authorization.

## Recovery

- Must not issue dispatch authorization.
- Must not inject dispatch authorization.
- Must not convert recovery request into dispatch permission.

## Boundary Seal

- Scheduler admission != dispatch permission.
- Dispatch authorization required.
- Recovery cannot issue dispatch authorization.
- No dispatch path created.
- Mutation disabled.
