# Activation Handoff Evidence Rules

Final decision: GO for evidence rules only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This document defines evidence required before any future activation execution handoff may be consumed.

## Required Evidence

- Handoff evidence is required.
- Ownership evidence is required.
- Decision evidence is required.
- Audit trail is required.
- Evidence reference is required on the handoff object.
- Audit reference is required on the handoff object.

## Evidence Rules

- Handoff evidence must identify the handoff intent and handoff state.
- Ownership evidence must identify the runtime owner.
- Decision evidence must prove owner approval.
- Audit trail must preserve activation, approval, scheduling, and execution actors.

## Missing Evidence

Missing evidence: NO-GO.

NO-GO when:

- handoff evidence is missing
- ownership evidence is missing
- decision evidence is missing
- audit trail is missing
- evidence reference is missing
- audit reference is missing

## Forbidden Behavior

- ACTIVE flag only is not evidence.
- Scheduler observation is not decision evidence.
- Executor readiness is not ownership evidence.
- Recovery request is not handoff evidence.
