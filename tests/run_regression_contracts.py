from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REGRESSION_TESTS = [
    Path("tests/test_scheduler_parser_helpers.py"),
    Path("tests/test_runtime_execution_contracts.py"),
    Path("tests/test_scheduler_extraction_boundary.py"),
    Path("tests/test_runtime_incident_contract.py"),
    Path("tests/test_runtime_aggregate_schema_lock_v2.py"),
    Path("tests/test_step_executor_runtime_event_integration_contract.py"),
    Path("tests/test_runtime_orchestrator_contract.py"),
    Path("tests/test_runtime_monitor_contract.py"),
    Path("tests/test_runtime_state_contract.py"),
    Path("tests/test_runtime_snapshot_contract.py"),
    Path("tests/test_runtime_event_replay_contract.py"),
    Path("tests/test_runtime_event_sink_contract.py"),
    Path("tests/test_runtime_event_channel_bridge_contract.py"),
    Path("tests/test_runtime_event_normalizer_contract.py"),
    Path("tests/test_runtime_ownership_contract.py"),
    Path("tests/test_runtime_mutation_guard_contract.py"),
    Path("tests/test_runtime_boundary_contract.py"),
    Path("tests/test_runtime_state_registry_contract.py"),
    Path("tests/test_runtime_event_bus_contract.py"),
    Path("tests/test_runtime_integration_adapter_contract.py"),
    Path("tests/test_runtime_hook_controller_contract.py"),
    Path("tests/test_runtime_lifecycle_pipeline_contract.py"),
    Path("tests/test_runtime_execution_session_contract.py"),
    Path("tests/test_runtime_replay_engine_contract.py"),
    Path("tests/test_runtime_recovery_coordinator_contract.py"),
    Path("tests/test_runtime_recovery_audit_contract.py"),
    Path("tests/test_runtime_policy_engine_contract.py"),
    Path("tests/test_runtime_execution_gate_contract.py"),
    Path("tests/test_runtime_gate_integration_contract.py"),
    Path("tests/test_runtime_intent_classifier_contract.py"),
    Path("tests/test_runtime_intent_gate_router_contract.py"),
    Path("tests/test_runtime_operation_registry_contract.py"),
    Path("tests/test_runtime_capability_resolver_contract.py"),
    Path("tests/test_runtime_capability_dispatcher_contract.py"),
    Path("tests/test_runtime_execution_transaction_contract.py"),
    Path("tests/test_runtime_transaction_orchestrator_contract.py"),
    Path("tests/test_runtime_execution_planner_contract.py"),
    Path("tests/test_runtime_plan_executor_contract.py"),
    Path("tests/test_runtime_execution_graph_contract.py"),
    Path("tests/test_runtime_operation_contract.py"),
    Path("tests/test_runtime_transaction_contract.py"),
    Path("tests/test_execution_plan_contract.py"),
    Path("tests/test_execution_plan_snapshot_contract.py"),
    Path("tests/test_execution_replay_contract.py"),
    Path("tests/test_execution_audit_contract.py"),
    Path("tests/test_rollback_verification_contract.py"),
    Path("tests/test_runtime_evidence_bundle_contract.py"),
    Path("tests/test_runtime_evidence_serialization_contract.py"),
    Path("tests/test_runtime_evidence_persistence_contract.py"),
]


def run_test(test_path: Path) -> int:
    full_path = PROJECT_ROOT / test_path
    if not full_path.exists():
        print(f"[regression] MISSING: {test_path}")
        return 1

    print("=" * 80)
    print(f"[regression] RUN: {test_path}")
    print("=" * 80)

    result = subprocess.run(
        [sys.executable, str(full_path)],
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode == 0:
        print(f"[regression] PASS: {test_path}")
    else:
        print(f"[regression] FAIL: {test_path}")

    return int(result.returncode)


def main() -> int:
    failures = 0

    for test_path in REGRESSION_TESTS:
        failures += 1 if run_test(test_path) != 0 else 0

    print("=" * 80)
    if failures:
        print(f"[regression] FAILED: {failures}/{len(REGRESSION_TESTS)} test files failed")
        return 1

    print(f"[regression] ALL PASS: {len(REGRESSION_TESTS)} test files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
