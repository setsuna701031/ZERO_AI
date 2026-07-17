# ZERO Operator Dashboard v1 — Release Gate Specification

Last verified: 2026-07-13

This specification is executable. A release is eligible only when every required test below passes through the production path. Run the gate with `pytest -q tests/test_runtime_invariant_*.py`.

| Invariant | Production contract | Automated test | Evidence | Required | Gate |
|---|---|---|---|:---:|:---:|
| Command / Query Separation | Goal Operations / Goal Controller | `tests/test_runtime_invariant_query.py` | Repeated queries preserve every persisted byte; all read-only POST routes return 403 | Yes | pytest PASS |
| Dashboard GET and Start/Stop Zero Side Effect | Goal Operations source ownership | `tests/test_runtime_invariant_zero_side_effect.py` | Before/after persisted SHA-256 map equality; no Dashboard state files | Yes | pytest PASS |
| Cross-root Persisted Manifest Equality | Operations source manifest v1 | `tests/test_runtime_invariant_manifest.py` | Goal, Mission, Session, Approval, Event, Memory, Reflection roots remain 100% equal | Yes | pytest PASS |
| Projection Contract Compatibility | Goal Operations projection v1 | `tests/test_runtime_invariant_contract.py` | Contract/version/kind and required public field names are frozen | Yes | pytest PASS |
| Fingerprint Stability and Tamper Detection | Operations fingerprint contract | `tests/test_runtime_invariant_fingerprint.py` | Three identical fingerprints; changed projection fails validation | Yes | pytest PASS |
| Overview HTTP Body/Header Determinism | Dashboard HTTP read facade | `tests/test_runtime_invariant_snapshot.py` | Three byte-identical bodies and header maps; UTF-8 byte length verified | Yes | pytest PASS |
| Deterministic Projection Gate | All five Goal Operations reads | `tests/test_runtime_invariant_projection.py` | Overview, Inspection, Timeline, Health, Approvals each queried 10 times with identical bodies, identities, fingerprints, and headers | Yes | pytest PASS |
| Shared Reference Time and Approval TTL | Time provider / Approval contract | `tests/test_runtime_invariant_ttl.py` | Fixed reference clock; token and approved Mission expiration fail closed before mutation | Yes | pytest PASS |
| Runtime Mission Budget | Runtime Mission budget observation v1 | `tests/test_runtime_invariant_budget.py` | Overview and Health budget/count/capacity projections agree | Yes | pytest PASS |
| Starvation Protection | Goal Daemon round-robin | `tests/test_runtime_invariant_starvation.py` | Every eligible Goal selected over 100 cycles; distribution delta ≤ 1 | Yes | pytest PASS |
| Replay Prevention and Controller Singleton | Dashboard action result / Goal Controller | `tests/test_runtime_invariant_replay.py` | Duplicate action is a replay, not a second mutation; factory called once | Yes | pytest PASS |
| Cross-goal Mission/Session Ownership | Goal Operations reference health | `tests/test_runtime_invariant_ownership.py` | Shared Mission and Session ownership is classified critical | Yes | pytest PASS |
| Runtime Upgrade Compatibility | Frozen v1 persisted runtime | `tests/test_runtime_invariant_upgrade.py` | New read surface loads Overview, Inspection, Timeline, Health and references without repair, fingerprint change, or new state | Yes | pytest PASS |

## Architectural release conditions

- GET: HTTP validation → `OperatorDashboardReadService` → `GoalOperationsService` → deterministic serialization.
- POST: HTTP validation → `OperatorDashboardActionService` → process-singleton `RuntimeGoalController` → persisted runtime result.
- Dashboard keeps only process-local operational counters, idempotency results, and confirmation sessions.
- Dashboard never creates `dashboard.db`, `dashboard.json`, `dashboard.cache`, or another runtime source of truth.
- Existing runtime security headers remain fixed: Content-Type, Content-Length, Cache-Control, Content-Security-Policy, X-Content-Type-Options, Referrer-Policy, and frame protection.

## v1.1 UI stability and clean shutdown gate

- Polling has one timer and one in-flight refresh cycle. Hidden/pagehide aborts the cycle; visibility restoration starts exactly one immediate refresh. Retry delay is capped at 60 seconds.
- Overview metrics, Goals, Pending Approvals, and Health each own a display fingerprint and render state. Unchanged data does not enter that region's renderer.
- Fixed header/title nodes are never recreated. Metrics and keyed Goal, Approval, and Health nodes retain identity while their text, state class, or progress changes.
- `tests/operator_dashboard_dom_identity_harness.js` executes 10 unchanged refreshes plus health-only, Goal-add, and Approval-add updates and verifies node identity by object reference.
- Server lifecycle is process-local and thread-safe: `created → starting → running → stopping → stopped`, with `failed` for fail-closed startup errors.
- Shutdown is idempotent and performs server shutdown, socket close, and a five-second-bounded join. Browser launch and request workers cannot keep the process alive.
- Windows binds exclusively while running and releases the socket for immediate same-port restart after Ctrl+Break/Ctrl+C shutdown.
