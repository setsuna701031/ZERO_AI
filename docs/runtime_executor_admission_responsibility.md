# Runtime Executor Admission Responsibility Matrix

Final decision: GO for responsibility boundary only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This matrix defines responsibility after scheduler dispatch authorization and before executor execution.

## Runtime Owner

- Owns activation decision.
- Owns owner-approved handoff.
- Must not execute.
- Must not create executor path.

## Scheduler

- May hold dispatch authorization as a prior boundary artifact.
- Must not call executor directly.
- Scheduler is not executor owner.
- Must not bypass executor admission.
- Must not convert dispatch authorization into execution permission.

## Executor

- Executor admission required.
- Must verify handoff chain.
- Must verify dispatch authorization.
- Must verify dispatch evidence.
- Must make executor admission decision.
- Must record executor admission audit.
- Must not self admit.
- Must not execute missing executor admission.

## Recovery

- Must not call executor.
- Must not inject executor admission.
- Must not convert recovery request into executor admission.

## Boundary Seal

- Dispatch authorization != execution permission.
- Executor admission required.
- Missing executor admission cannot execute.
- No executor path created.
- Mutation disabled.
