# Stage15C — Gate Authority Reconciliation

## Decision

- GF-003 classification: **inventory_drift**
- Runtime bug: **false**
- Actual runtime owner: `core.runtime.task_runtime.project_runtime_status`
- Canonical projection coverage: 10 / 10 missing-baseline files
- Current tracked non-owner direct writers: `core/runtime/task_runner.py`

## Authority reconciliation

- Expected inventory owner files: `core/runtime/runtime_dispatcher.py`, `core/runtime/runtime_session_resume.py`, `core/runtime/runtime_state_machine.py`, `core/runtime/task_runtime.py`, `core/tasks/task_state.py`
- Seal rule source: `tools/aer_ownership_migration_plan_stage14.py:155-175,664-673`
- Failing assertion source: `tests/test_runtime_status_ownership_inventory.py:112`
- Failing assertion: `EXPECTED_HIGH_RISK_FILES <= high_risk`

## Evidence trace

- `GF003-E01` — **runtime_owner** — project_runtime_status is the canonical status write boundary; it validates a dict target, assigns payload['status'], and returns that payload. Source: `core/runtime/task_runtime.py:75`
- `GF003-E02` — **runtime_callers** — All eleven EXPECTED_HIGH_RISK_FILES entries call project_runtime_status; ten have no tracked direct status assignment, while task_runner.py remains the only tracked non-owner direct writer. Source: `live AST scan of core/runtime, core/tasks, and core/adaptive`
- `GF003-E03` — **inventory_rule** — ALLOWED_FILES names five accepted owner files, while EXPECTED_HIGH_RISK_FILES is a fixed eleven-file residue baseline. Source: `tests/test_runtime_status_ownership_inventory.py:14-48`
- `GF003-E04` — **failing_assertion** — The assertion requires every fixed EXPECTED_HIGH_RISK_FILES entry to appear among current tracked direct status assignments. Source: `tests/test_runtime_status_ownership_inventory.py:98-115`
- `GF003-E05` — **stage14_seal** — Stage14 records the assertion failure as seal evidence and requires ownership/evidence graph stability; its generic runtime-ownership drift rule does not require reintroducing direct status writes. Source: `docs/architecture/runtime_native_ownership/aer_ownership_migration_plan_stage14.json#validation_results/seal_blockers`
- `GF003-E06` — **non_mainline_track** — Six non-mainline observability records remain separately reported; GF-003 does not erase or reclassify them. Source: `docs/architecture/runtime_native_ownership/aer_ownership_migration_plan_stage14.json#non_mainline_issues`
- `GF003-E07` — **stage15a_generator** — Stage15A readiness consumes a hardcoded historical VALIDATION_RESULTS object, so rerunning the generator cannot observe a newly passing live suite without generator correction. Source: `tools/aer_wave0_execution_gate_stage15a.py:34-60,192-205`
- `GF003-E08` — **downstream_artifacts** — Stage15A.1 preserves GF-003 as runtime-status inventory drift; Stage15A.2 correctly declines to manufacture direct writes and leaves reconciliation gated. Source: `docs/architecture/runtime_native_ownership/aer_wave0_gate_failure_inventory_stage15a1.json and docs/architecture/runtime_native_ownership/gate_failure_closure_plan_stage15a2.json`

## Classification basis

- The runtime uses the named canonical status projection boundary in ten files that the inventory still expects to be direct writers.
- The failing assertion compares a historical fixed residue set against current direct-write AST findings.
- Stage14 itself describes the failure as an inventory difference requiring reconciliation, not as proof of an illegal runtime write.

## Migration plan

### 1. runtime status ownership inventory source of truth

Generate a typed inventory with separate canonical-owner files, canonical projection callers, tracked non-owner direct writers, and non-mainline observability records.

Completion gate: The generated inventory reports task_runtime.project_runtime_status as owner, ten projected expected files, task_runner.py as the current tracked direct-writer residue, and S14-NM-001..006 unchanged.

### 2. tests/test_runtime_status_ownership_inventory.py

In a separately authorized change, replace the stale fixed direct-writer subset assertion with assertions over the typed inventory: canonical owner exists, projection callers are explicit, and no untracked direct writer appears.

Completion gate: The ownership suite passes without adding direct status writes to projection callers.

### 3. Stage14 successor seal definition

Bind status ownership seal evidence to the typed inventory and fail only on canonical-owner drift, unexpected direct writers, missing projection provenance, or loss of non-mainline records.

Completion gate: Seal semantics preserve runtime_ownership_drift and evidence_graph_drift without treating successful projection migration as missing evidence.

### 4. tools/aer_wave0_execution_gate_stage15a.py

In a separately authorized successor generator, replace hardcoded VALIDATION_RESULTS readiness input with a versioned live validation-result artifact; retain historical failures as immutable evidence only.

Completion gate: A rerun reflects current suite results while Stage15A artifacts remain unchanged.

### 5. Wave 0 authorization reconciliation

Run artifact consistency and the corrected ownership inventory suite, then issue a new reconciliation decision rather than rewriting Stage14 or Stage15A evidence.

Completion gate: GF-003 is closed as inventory_drift, six non-mainline records remain reported, and no runtime/test change is hidden in artifact regeneration.

## Non-Mainline Issue Reporting

- 6 / 6 Stage14 non-mainline observability records preserved.

## Validation

- Artifact consistency: pass
- Classification selected exactly once: true
- Runtime modified: false
- Tests modified: false
- Stage15A artifacts modified: false
