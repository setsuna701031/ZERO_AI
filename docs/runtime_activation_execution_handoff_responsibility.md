# Runtime Owner Handoff Responsibility Matrix

Final decision: GO for responsibility boundary only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This matrix defines which authority may create, consume, or reject a future execution handoff.

## Runtime Owner

- MAY create handoff intent.
- MUST attach evidence.
- MUST approve or reject the handoff decision.
- MUST NOT execute.

## Scheduler

- MAY consume approved handoff.
- MUST require handoff before scheduling execution.
- MUST NOT create handoff.
- MUST NOT infer execution permission from ACTIVE state.
- MUST NOT self authorize execution.

## Executor

- MAY execute handed off work.
- MUST require handoff before accepting work.
- MUST require explicit execution permission.
- MUST NOT activate runtime.
- MUST NOT accept activation directly.

## Recovery

- MUST NOT create handoff.
- MUST NOT approve handoff.
- MUST NOT convert recovery request into execution permission.

## Boundary Seal

- ACTIVE != execution permission.
- Runtime owner != executor.
- Scheduler != runtime owner.
- Recovery != handoff authority.
