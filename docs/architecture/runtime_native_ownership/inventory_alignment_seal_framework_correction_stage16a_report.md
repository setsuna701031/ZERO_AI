# Stage16A — Inventory Alignment & Seal Framework Correction

## Decision

- GF-003 source: stale direct-writer baseline in `tests/test_runtime_status_ownership_inventory.py`.
- Canonical status owner: `core.runtime.task_runtime.project_runtime_status`.
- Inventory, seal definitions, and readiness generation all require migration to typed canonical-ownership evidence.
- `core/runtime/task_runner.py` is transitional compatibility-layer code that is a true ownership violation under the canonical model; it is not a legitimate owner write.
- Runtime modifications performed: false.

## Exact migration set

### Existing files to migrate

1. `tests/test_runtime_status_ownership_inventory.py`
   - Replace the historical `EXPECTED_HIGH_RISK_FILES <= high_risk` direct-write assertion.
   - Assert a typed inventory containing canonical owners, projection clients, tracked direct-writer residue, and non-mainline observations.
2. `tests/test_runtime_status_write_authority_seal.py`
   - Consume the same typed inventory and canonical owner policy.
   - Keep unexpected direct writers fatal; do not allow-list `task_runner.py`.
3. `tools/aer_ownership_migration_plan_stage14.py`
   - Preserve Stage14 output as immutable evidence.
   - Move successor seal semantics from historical counts/hashes to typed owner, projection, direct-writer, bridge, and non-mainline records.
4. `tools/aer_wave0_execution_gate_stage15a.py`
   - Preserve Stage15A output as immutable evidence.
   - Replace hardcoded `VALIDATION_RESULTS` as the readiness input with a versioned live validation result artifact.

### New successor artifacts required

1. `docs/architecture/runtime_native_ownership/runtime_status_ownership_inventory_v2.json`
2. `docs/architecture/runtime_native_ownership/runtime_ownership_seal_v2.json`
3. `docs/architecture/runtime_native_ownership/runtime_readiness_validation_v2.json`
4. A successor Wave 0 gate artifact generated from those three versioned inputs.

## TaskRunner residue

The strict ownership seal finds 11 direct status assignments in the appended Stage3B compatibility/consolidation wrappers at lines 5660, 5765, 5770, 5820, 5825, 5929, 5931, 5933, 5957, 5961, and 5965. The same area monkey-patches `TaskRunner.run_task_tick` and `TaskRunner.run_task`.

Classification:

- implementation origin: transitional bridge;
- canonical gate classification: true ownership violation;
- legitimate owner write: no.

## Executable correction order

1. Create the typed inventory v2 from the live AST scan and canonical projection calls.
2. Migrate both ownership tests to the shared inventory semantics.
3. Define the successor seal without rewriting Stage14 evidence.
4. Replace Stage15A hardcoded readiness input in a successor generator; do not rewrite Stage15A artifacts.
5. Run compileall, the Stage15A ownership/blocker suite, and the strict status-write authority seal.
6. Record GF-003 closed as inventory drift only if the typed inventory still exposes `task_runner.py` as direct-writer residue.
7. Execute a separately authorized pre-Wave1 TaskRunner residue-closure wave, routing status projection through the canonical owner and retiring the appended wrappers.
8. Re-run the live successor gate; authorize Wave1 only after all live freeze and seal checks pass.

## Expected gate state

- Immediately after framework migration only: inventory-drift check passes; successor seal fails on `core/runtime/task_runner.py`; Wave1 remains unauthorized.
- After TaskRunner residue closure and green validation: successor Wave 0 passes and Wave1 becomes authorizable.
- First executable post-alignment wave: TaskRunner status-owner residue closure (pre-Wave1 correction wave), followed by Wave1 authority-context migration.

## Validation observed

- `compileall -q core tests tools`: pass.
- Stage15A ownership/blocker suite: 66 passed, 7 subtests passed, 1 failed; sole failure is stale inventory GF-003.
- Focused Stage15A three-test suite: scheduler and repair-chain tests pass; inventory test fails.
- Strict status-write authority seal: 2 failed, 2 passed; both failures identify only `core/runtime/task_runner.py`.

## Remaining freeze/seal blockers

- Live framework blocker: stale inventory assertion.
- Live seal blocker: 11 direct TaskRunner status writes in transitional wrappers.
- Readiness blocker: Stage15A generator embeds historical validation results and cannot observe current remediation.
- Historical Stage14 records (113 freeze records and 15 compatibility bridges) remain immutable evidence and must be re-evaluated by the successor live gate, not silently declared closed.

## Non-Mainline Issue Reporting

All six records remain preserved as observability-only evidence:

- `S14-NM-001` through `S14-NM-005`: `core/tasks/scheduler.py`
- `S14-NM-006`: `core/tasks/scheduler_core/runtime_overlay_helpers.py`

They are not reclassified as GF-003 and do not authorize direct status writes.
