# Runtime Activation Scheduler Admission Responsibility Matrix

Final decision: GO for responsibility boundary only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This matrix defines responsibility for future scheduler admission after execution handoff creation.

## Runtime Owner

- Owns activation decision.
- Owns handoff approval decision.
- Must provide owner approval before scheduler admission.
- Must not dispatch.
- Must not execute.

## Scheduler

- May perform scheduler admission check against an approved execution handoff.
- Must require execution handoff.
- Must require owner approval.
- Must require handoff evidence.
- Must record admission audit.
- Must reject admission when required evidence is missing.
- Must not create handoff.
- Must not approve owner decision.
- Must not self authorize.
- Must not dispatch from ACTIVE alone.

## Executor

- Must not treat scheduler admission as execution without handoff permission.
- Must not execute rejected admission.
- Must not activate runtime.

## Recovery

- Must not create handoff.
- Must not inject handoff.
- Must not request recovery-created handoff admission.

## Boundary Seal

- ACTIVE != scheduler admission.
- Scheduler != runtime owner.
- Scheduler cannot self authorize.
- Recovery cannot inject handoff.
- Mutation disabled.
