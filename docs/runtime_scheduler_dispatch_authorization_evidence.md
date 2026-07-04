# Runtime Scheduler Dispatch Authorization Evidence Rules

Final decision: GO for evidence rules only.

Runtime activation remains disabled. Runtime mutation remains disabled.

## Purpose

This document defines evidence required before any future scheduler dispatch authorization may be considered.

## Required Evidence

- Owner-approved handoff required.
- Dispatch evidence required.
- Dispatch audit required.
- Scheduler admission evidence required.
- Evidence must identify the owner-approved handoff.
- Evidence must identify dispatch authorization state.
- Evidence must prove authorization source is not recovery.

## Missing Evidence

Missing evidence: NO-GO.

NO-GO when:

- owner-approved handoff is missing
- dispatch evidence is missing
- dispatch audit is missing
- authorization source is recovery-issued
- scheduler relies on admission alone
- dispatch authorization is missing

## Evidence Non-Substitutes

- Scheduler admission != dispatch permission.
- Admitted handoff is not dispatch authorization.
- ACTIVE state is not dispatch authorization.
- Recovery request is not dispatch evidence.

## Forbidden Behavior

- Dispatch without evidence.
- Dispatch without audit.
- Missing dispatch authorization cannot execute.
- No dispatch path created.
