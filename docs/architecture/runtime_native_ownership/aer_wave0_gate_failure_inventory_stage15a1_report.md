# Stage15A.1 — Wave 0 Gate Failure Decomposition

## Decision

- Failing tests: 3
- Distinct gate failures: 3
- Highest risk: `S15A1-GF-001` — `tests/test_scheduler_runtime_ownership_closure.py::test_scheduler_constructs_one_endpoint_and_one_delegation_boundary`
- First authorizable wave: Wave 1: authority context migration, after all minimum_gate_set conditions pass
- Minimum gate set: `S15A1-GF-001`, `S15A1-GF-002`, `S15A1-GF-003`

## Gate Failure Inventory

### S15A1-GF-001

- Test: `tests/test_scheduler_runtime_ownership_closure.py::test_scheduler_constructs_one_endpoint_and_one_delegation_boundary`
- Assertion: `assert direct_calls == []`
- Categories: `scheduler_direct_call_seal`
- Owner/domain: `core.tasks.scheduler.Scheduler` / `scheduler`
- Blocked wave: Wave 3: scheduler direct-call seal
- Blocker IDs: `S13A-SCHED-001`, `S13A-SCHED-002`, `S13A-SCHED-003`, `S13A-SCHED-004`, `S13A-SCHED-005`, `S13A-SCHED-006`, `S13A-SCHED-007`, `S13A-SCHED-008`, `S13A-SCHED-009`, `S13A-SCHED-011`, `S13A-SCHED-012`, `S13A-SCHED-015`, `S13A-SCHED-016`, `S13A-SCHED-017`, `S13A-SCHED-018`, `S13A-SCHED-019`, `S13A-SCHED-020`, `S13A-SCHED-022`, `S13A-SCHED-023`, `S13A-SCHED-027`, `S13A-SCHED-028`, `S13A-SCHED-029`, `S13A-SCHED-030`, `S13A-SCHED-031`, `S13A-SCHED-032`, `S13A-SCHED-033`, `S13A-SCHED-034`, `S13A-SCHED-035`, `S13A-SCHED-036`, `S13A-SCHED-037`, `S13A-SCHED-038`, `S13A-SCHED-039`, `S13A-SCHED-040`, `S13A-SCHED-041`, `S13A-SCHED-042`, `S13A-SCHED-043`, `S13A-SCHED-044`, `S13A-SCHED-045`, `S13A-SCHED-046`, `S13A-SCHED-047`, `S13A-SCHED-048`, `S13A-SCHED-049`, `S13A-SCHED-050`, `S13A-SCHED-051`, `S13A-SCHED-052`
- Unlock: The named scheduler ownership test passes with direct_calls == []; all six Stage14 direct StepExecutor call seals are absent and Wave 3 validation passes.
- Criticality: `critical`

### S15A1-GF-002

- Test: `tests/test_runtime_native_autonomous_repair_chain_v2_integration.py::test_step_executor_autonomous_repair_chain_handler`
- Assertion: `assert result["ok"] is True`
- Categories: `repair_chain_dependency`, `goal_lineage_integrity`, `runtime_session_boundary`
- Owner/domain: `core.runtime.step_executor.StepExecutor` / `repairchain / lineage / runtime_session`
- Blocked wave: Wave 7: repairchain recovery / retry / duplicate repair
- Blocker IDs: `S13C-SE-028`
- Unlock: The named repair-chain integration test passes with result['ok'] is True and S13C-SE-028 validation_gate passes without repairchain, lineage, or runtime-session regression.
- Criticality: `high`

### S15A1-GF-003

- Test: `tests/test_runtime_status_ownership_inventory.py::test_runtime_status_ownership_inventory_is_explicit`
- Assertion: `assert EXPECTED_HIGH_RISK_FILES <= high_risk`
- Categories: `runtime_status_ownership_drift`
- Owner/domain: `runtime status ownership inventory` / `non_mainline_observability / runtime_status_ownership`
- Blocked wave: Wave 10: seal validation
- Blocker IDs: `S14-NM-001`, `S14-NM-002`, `S14-NM-003`, `S14-NM-004`, `S14-NM-005`, `S14-NM-006`
- Unlock: The named inventory test passes: every EXPECTED_HIGH_RISK_FILES entry is present in the scan findings, with the Stage14 non-mainline observability report retained.
- Criticality: `critical`

## Categories

- `scheduler_direct_call_seal`: S15A1-GF-001
- `authority_propagation`: none
- `runtime_status_ownership_drift`: S15A1-GF-003
- `goal_lineage_integrity`: S15A1-GF-002
- `runtime_session_boundary`: S15A1-GF-002
- `repair_chain_dependency`: S15A1-GF-002
- `other`: none

## Wave Impact Graph

- `S15A1-GF-001` → Wave 3: scheduler direct-call seal → Wave 4: taskrunner execution ownership, Wave 5: stepexecutor fallback / execution ownership, Wave 6: lineage + runtime-session boundary, Wave 7: repairchain recovery / retry / duplicate repair, Wave 8: compatibility bridge retirement, Wave 9: freeze validation, Wave 10: seal validation → freeze blocked → seal blocked
- `S15A1-GF-002` → Wave 7: repairchain recovery / retry / duplicate repair → Wave 8: compatibility bridge retirement, Wave 9: freeze validation, Wave 10: seal validation → freeze blocked → seal blocked
- `S15A1-GF-003` → Wave 10: seal validation → seal endpoint → freeze blocked → seal blocked

## Authorization

- Removing any one failure alone does not authorize Wave 1; two failures remain.
- Removing all three failures authorizes Wave 1 only if all other Stage15A locks remain passing and no new failure appears.
- Freeze impact: Wave 0 remains failed; Wave 1 and all sequential downstream waves remain unauthorized.
- Seal impact: Wave 10 remains blocked by all three preserved failures; status inventory drift is explicit seal evidence.

## Non-Mainline Issue Reporting

- 6 / 6 preserved in observability-only track
- No non-mainline issue was reclassified or repaired.

## Validation

- Generator: pass
- Compileall: pass
- Limited pytest: expected_failures_reproduced (3/3 failures reproduced)

## Scope attestation

- Production runtime touched: false
- Tests touched: false
- Blockers fixed: false
