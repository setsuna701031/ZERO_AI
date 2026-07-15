# ZERO Runtime v1 Functional Baseline

Baseline version: `zero.runtime.baseline.v1`  
Release candidate: `1.0.0-rc.1`  
Recorded: `2026-07-13`

This is a release functional baseline, not a benchmark. Values describe bounded completion and required observable results in the focused tests; they are not performance service-level objectives.

| Operation | RC functional baseline | Evidence |
| --- | --- | --- |
| Dashboard Startup | Loopback socket reaches `running`; startup and readiness complete within the focused test timeout | Dashboard lifecycle and real subprocess tests |
| Goal Creation | Deterministic goal identity and sealed persisted goal/index are produced once | Goal Runtime and Goal CLI tests |
| Goal Resume | Valid paused goal resumes through the controller; invalid transitions fail closed | Goal Controller and Goal CLI tests |
| Daemon Cycle | One bounded cycle respects mission budget, fairness, and configured per-cycle limits | Goal Daemon and invariant budget/starvation tests |
| Operations Query | Deterministic read projection; repeated query is byte-invariant | Goal Operations and invariant projection tests |
| Health Query | Deterministic readiness/degradation projection with no persisted mutation | Operations Health and zero-side-effect tests |
| Timeline Query | Deterministic persisted event ordering and fingerprint | Operations Timeline and invariant projection tests |

## Interpretation

- A baseline passes when the operation finishes within its existing focused-test bound and satisfies its deterministic/ownership contract.
- A slower result is a release investigation signal, not automatically a contract break.
- Baseline updates require measured evidence, documentation synchronization, and the three freeze reviews.
- Full soak, load, scale, and production-environment measurements remain outside the RC focused gate.
