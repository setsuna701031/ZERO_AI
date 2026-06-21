# Stage15A.2 — Gate Failure Closure Planning

## Closure decision

- Gate to clear first: `S15A1-GF-001` — It is the highest-risk failure and has the earliest Stage14-assigned remediation wave.
- Smallest scoped package: `S15A2-RP-001`
- Currently executable: `false`
- First gate-remediation wave: Wave 3: scheduler direct-call seal
- Expected Wave 1 authorization: All Stage15A invariant locks remain passing; S15A1-GF-001, S15A1-GF-002, and S15A1-GF-003 all satisfy their closure conditions; the limited ownership/blocker suites pass; and no new validation failure appears.

## Execution topology

- Status: `execution_dependency_deadlock`
- Consequence: No runtime remediation package is executable under the current authorization topology without separate gate-policy authority; this plan does not alter that policy.

## S15A1-GF-001

- Root cause: The scheduler ownership AST scan finds six direct StepExecutor.execute_step calls where the delegation-boundary contract requires an empty direct-call set.
- Owner: `core.tasks.scheduler.Scheduler`
- Affected symbols: `_zero_scheduler_run_one_step_v1`, `_zero_scheduler_run_one_step_v2`, `_zero_scheduler_run_one_step_v3`, `_zero_scheduler_run_one_step_v4`, `Scheduler.run_one_step`, `StepExecutor.execute_step`
- Affected blockers: `S13A-SCHED-001`, `S13A-SCHED-002`, `S13A-SCHED-003`, `S13A-SCHED-004`, `S13A-SCHED-005`, `S13A-SCHED-006`, `S13A-SCHED-007`, `S13A-SCHED-008`, `S13A-SCHED-009`, `S13A-SCHED-011`, `S13A-SCHED-012`, `S13A-SCHED-015`, `S13A-SCHED-016`, `S13A-SCHED-017`, `S13A-SCHED-018`, `S13A-SCHED-019`, `S13A-SCHED-020`, `S13A-SCHED-022`, `S13A-SCHED-023`, `S13A-SCHED-027`, `S13A-SCHED-028`, `S13A-SCHED-029`, `S13A-SCHED-030`, `S13A-SCHED-031`, `S13A-SCHED-032`, `S13A-SCHED-033`, `S13A-SCHED-034`, `S13A-SCHED-035`, `S13A-SCHED-036`, `S13A-SCHED-037`, `S13A-SCHED-038`, `S13A-SCHED-039`, `S13A-SCHED-040`, `S13A-SCHED-041`, `S13A-SCHED-042`, `S13A-SCHED-043`, `S13A-SCHED-044`, `S13A-SCHED-045`, `S13A-SCHED-046`, `S13A-SCHED-047`, `S13A-SCHED-048`, `S13A-SCHED-049`, `S13A-SCHED-050`, `S13A-SCHED-051`, `S13A-SCHED-052`
- Affected waves: Wave 3: scheduler direct-call seal, Wave 4–10 downstream, Wave 1 authorization through the failed Wave 0 aggregate gate
- Minimum remediation: One scheduler ownership package covering the six evidenced call sites in core/tasks/scheduler.py and their single delegation-boundary validation contract.
- Rollback risk: `critical` — Rollback the entire wave if any included blocker validation gate fails or ownership/evidence drift is detected.
- Validation suites: `tests/test_scheduler_runtime_ownership_closure.py`, `tests/test_runtime_execution_ownership_seal.py`, `tests/test_runtime_ownership_execution_path_seal.py`
- Closure condition: The named scheduler ownership test passes with direct_calls == []; all six Stage14 direct StepExecutor call seals are absent and Wave 3 validation passes.

## S15A1-GF-002

- Root cause: For the autonomous_repair_chain test input, StepExecutor.execute_step returns result['ok'] == false instead of the required true handler contract.
- Owner: `core.runtime.step_executor.StepExecutor`
- Affected symbols: `StepExecutor.execute_step`, `StepExecutor._handle_autonomous_repair_chain_step`
- Affected blockers: `S13C-SE-028`
- Affected waves: Wave 7: repairchain recovery / retry / duplicate repair, Wave 8–10 downstream, Wave 1 authorization through the failed Wave 0 aggregate gate
- Minimum remediation: One blocker-scoped handler-contract package for S13C-SE-028, preserving repairchain, lineage, and runtime-session outputs.
- Rollback risk: `high` — Rollback if repair eligibility, recovery continuation, retry limits, duplicate suppression, lineage, or repair-session persistence diverges.
- Validation suites: `tests/test_runtime_native_autonomous_repair_chain_v1.py`, `tests/test_runtime_native_autonomous_repair_chain_v2_integration.py`, `tests/test_runtime_native_autonomous_repair_chain_seal_v1.py`, `tests/test_runtime_blockers.py`, `tests/test_runtime_execution_ownership_migration_contract.py`, `tests/test_runtime_ownership_isolation_fabric_seal_v1.py`, `tests/test_runtime_ownership_contract.py`, `tests/test_runtime_status_ownership_inventory.py`
- Closure condition: The named repair-chain integration test passes with result['ok'] is True and S13C-SE-028 validation_gate passes without repairchain, lineage, or runtime-session regression.

## S15A1-GF-003

- Root cause: The explicit status-owner scan reports only core/runtime/task_runner.py while ten other EXPECTED_HIGH_RISK_FILES entries are absent, producing ownership-inventory evidence drift.
- Owner: `runtime status ownership inventory`
- Affected symbols: `Scheduler.get_queue_snapshot`, `Scheduler.get_queue_rows`, `Scheduler.approve_review_item`, `Scheduler.reject_review_item`, `Scheduler.get_review_queue`, `Scheduler._attach_autonomous_repair_chain_summary`, `EXPECTED_HIGH_RISK_FILES`, `high_risk status assignment scan`
- Affected blockers: `S14-NM-001`, `S14-NM-002`, `S14-NM-003`, `S14-NM-004`, `S14-NM-005`, `S14-NM-006`
- Affected waves: Wave 8: compatibility bridge/non-mainline retirement evidence, Wave 9: freeze validation, Wave 10: seal validation, Wave 1 authorization through the failed Wave 0 aggregate gate
- Minimum remediation: One evidence-reconciliation package for the ten missing scan findings and six Stage14 non-mainline observability records; runtime ownership evidence must satisfy the unchanged test contract.
- Rollback risk: `critical` — Rollback if reconciliation hides status writers, changes canonical status ownership, drops non-mainline evidence, or creates evidence-graph drift.
- Validation suites: `tests/test_runtime_status_ownership_inventory.py`, `tests/test_runtime_audit_artifact.py`
- Closure condition: The named inventory test passes: every EXPECTED_HIGH_RISK_FILES entry is present in the scan findings, with the Stage14 non-mainline observability report retained.

## Artifact consistency

- Status: pass
- Stage14 wave assignments preserved: true
- Stage15A authorization condition preserved: true
- Non-mainline reporting preserved: true

## Scope attestation

- Production runtime touched: false
- Tests touched: false
- Blockers fixed: false
