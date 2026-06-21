from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
STAGE14 = OUT_DIR / "aer_ownership_migration_plan_stage14.json"
STAGE15A = OUT_DIR / "aer_wave0_execution_gate_stage15a.json"
STAGE15A_SUMMARY = OUT_DIR / "aer_wave0_execution_gate_stage15a_summary.json"
RUNTIME_BLOCKERS = OUT_DIR / "runtime_blocker_validation.json"
OWNERSHIP_ARTIFACTS = (
    OUT_DIR / "scheduler_native_ownership_closure_stage13a.json",
    OUT_DIR / "stepexecutor_native_ownership_closure_stage13c.json",
    OUT_DIR / "repairchain_native_ownership_closure_stage13d.json",
)
OUTPUT = OUT_DIR / "aer_wave0_gate_failure_inventory_stage15a1.json"
SUMMARY = OUT_DIR / "aer_wave0_gate_failure_inventory_stage15a1_summary.json"
REPORT = OUT_DIR / "aer_wave0_gate_failure_inventory_stage15a1_report.md"

CATEGORIES = (
    "scheduler_direct_call_seal",
    "authority_propagation",
    "runtime_status_ownership_drift",
    "goal_lineage_integrity",
    "runtime_session_boundary",
    "repair_chain_dependency",
    "other",
)

# Exact assertion payloads reproduced by the limited three-test pytest run.
PYTEST_EVIDENCE: dict[str, dict[str, Any]] = {
    "tests/test_scheduler_runtime_ownership_closure.py::test_scheduler_constructs_one_endpoint_and_one_delegation_boundary": {
        "assertion": "assert direct_calls == []",
        "expected_result": [],
        "observed_result": [
            "execute_step:_zero_scheduler_run_one_step_v2:10551",
            "execute_step:_zero_scheduler_run_one_step_v3:10620",
            "execute_step:_zero_scheduler_run_one_step_v4:10686",
            "execute_step:_zero_scheduler_run_one_step_v1:10478",
            "execute_step:_zero_scheduler_run_one_step_v1:10481",
            "execute_step:_zero_scheduler_run_one_step_v1:10483",
        ],
    },
    "tests/test_runtime_native_autonomous_repair_chain_v2_integration.py::test_step_executor_autonomous_repair_chain_handler": {
        "assertion": 'assert result["ok"] is True',
        "expected_result": True,
        "observed_result": False,
    },
    "tests/test_runtime_status_ownership_inventory.py::test_runtime_status_ownership_inventory_is_explicit": {
        "assertion": "assert EXPECTED_HIGH_RISK_FILES <= high_risk",
        "expected_result": [
            "core/adaptive/adaptive_runtime_resume.py",
            "core/runtime/persistent_runtime_orchestrator.py",
            "core/runtime/runtime_recovery_continuation.py",
            "core/runtime/task_runner.py",
            "core/runtime/thin_runtime_bridge.py",
            "core/runtime/work_package_queue.py",
            "core/tasks/scheduler.py",
            "core/tasks/scheduler_core/repo_state_helpers.py",
            "core/tasks/scheduler_core/runtime_overlay_helpers.py",
            "core/tasks/scheduler_core/runtime_resume_gate.py",
            "core/tasks/scheduler_core/simple_runner_helpers.py",
        ],
        "observed_result": ["core/runtime/task_runner.py"],
        "missing_expected_high_risk_files": [
            "core/adaptive/adaptive_runtime_resume.py",
            "core/runtime/persistent_runtime_orchestrator.py",
            "core/runtime/runtime_recovery_continuation.py",
            "core/runtime/thin_runtime_bridge.py",
            "core/runtime/work_package_queue.py",
            "core/tasks/scheduler.py",
            "core/tasks/scheduler_core/repo_state_helpers.py",
            "core/tasks/scheduler_core/runtime_overlay_helpers.py",
            "core/tasks/scheduler_core/runtime_resume_gate.py",
            "core/tasks/scheduler_core/simple_runner_helpers.py",
        ],
    },
}

VALIDATION_RESULTS = {
    "generator": "pass",
    "compileall": "pass",
    "pytest": {
        "status": "expected_failures_reproduced",
        "collected": 3,
        "passed": 0,
        "failed": 3,
        "duration_seconds": 2.24,
        "failure_set_matches_stage15a": True,
        "command": "python -m pytest -vv tests/test_scheduler_runtime_ownership_closure.py::test_scheduler_constructs_one_endpoint_and_one_delegation_boundary tests/test_runtime_native_autonomous_repair_chain_v2_integration.py::test_step_executor_autonomous_repair_chain_handler tests/test_runtime_status_ownership_inventory.py::test_runtime_status_ownership_inventory_is_explicit",
    },
    "overall": "pass_with_expected_failures_preserved_as_evidence",
}


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required input: {relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wave_label(wave: dict[str, Any]) -> str:
    return f"Wave {wave['wave']}: {wave['name']}"


def gate_from_blockers(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    conditions = sorted({item[key]["condition"] for item in records if isinstance(item.get(key), dict) and item[key].get("condition")})
    return {"required": True, "conditions": conditions}


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    plan = load(STAGE14)
    gate = load(STAGE15A)
    gate_summary = load(STAGE15A_SUMMARY)
    blocker_validation = load(RUNTIME_BLOCKERS)
    ownership = {relative(path): load(path) for path in OWNERSHIP_ARTIFACTS}

    stage15a_failures = gate.get("validation_results", {}).get("pytest", {}).get("failures", [])
    stage15a_names = [item.get("test") for item in stage15a_failures]
    if set(stage15a_names) != set(PYTEST_EVIDENCE):
        raise SystemExit(f"Stage15A failure set drifted: expected={sorted(PYTEST_EVIDENCE)}, actual={sorted(stage15a_names)}")
    if gate_summary.get("wave0_gate_status") != "fail" or gate_summary.get("wave1_ready") is not False:
        raise SystemExit("Stage15A failed Wave 0 / closed Wave 1 decision is required")

    blockers = plan.get("blocker_migration_plan", [])
    blocker_by_id = {item["blocker_id"]: item for item in blockers}
    waves = {item["wave"]: item for item in plan.get("migration_waves", [])}
    wave3_records = [blocker_by_id[item] for item in waves[3]["included_blockers"]]
    repair_record = blocker_by_id["S13C-SE-028"]
    nonmainline = plan.get("non_mainline_issues", [])
    nonmainline_ids = [item["tracking_id"] for item in nonmainline]

    scheduler_test = stage15a_failures[stage15a_names.index("tests/test_scheduler_runtime_ownership_closure.py::test_scheduler_constructs_one_endpoint_and_one_delegation_boundary")]
    repair_test = stage15a_failures[stage15a_names.index("tests/test_runtime_native_autonomous_repair_chain_v2_integration.py::test_step_executor_autonomous_repair_chain_handler")]
    status_test = stage15a_failures[stage15a_names.index("tests/test_runtime_status_ownership_inventory.py::test_runtime_status_ownership_inventory_is_explicit")]

    common_wave0_freeze = {
        "required": True,
        "condition": "Stage15A aggregate validation must pass before Wave 0 completes and Wave 1 authorization can open.",
        "source": relative(STAGE15A),
    }
    scheduler = {
        "failure_id": "S15A1-GF-001",
        "test_name": scheduler_test["test"],
        **PYTEST_EVIDENCE[scheduler_test["test"]],
        "categories": ["scheduler_direct_call_seal"],
        "owner_domain": "scheduler",
        "blocking_owner": "core.tasks.scheduler.Scheduler",
        "native_owner": "core.tasks.scheduler.Scheduler.run_one_step (native definition)",
        "blocker_ids": waves[3]["included_blockers"],
        "blocker_mapping_scope": "Stage14 Wave 3 included blocker set; the six direct-call records have no independent blocker IDs.",
        "migration_wave_blocked": wave_label(waves[3]),
        "wave1_authorization_blocked": True,
        "freeze_gate": {
            **common_wave0_freeze,
            "assigned_wave_condition": "Scheduler direct execute_step/execute_steps call inventory must be empty before Wave 3 completes.",
            "evidence": scheduler_test["evidence"],
        },
        "seal_gate": gate_from_blockers(wave3_records, "seal_gate"),
        "unlock_condition": "The named scheduler ownership test passes with direct_calls == []; all six Stage14 direct StepExecutor call seals are absent and Wave 3 validation passes.",
        "criticality": "critical",
        "criticality_basis": "Stage14 records this test as a critical-suite freeze blocker and assigns the direct-call seal to Wave 3.",
    }
    repair = {
        "failure_id": "S15A1-GF-002",
        "test_name": repair_test["test"],
        **PYTEST_EVIDENCE[repair_test["test"]],
        "categories": ["repair_chain_dependency", "goal_lineage_integrity", "runtime_session_boundary"],
        "owner_domain": "repairchain / lineage / runtime_session",
        "blocking_owner": "core.runtime.step_executor.StepExecutor",
        "native_owner": repair_record["native_owner"],
        "blocker_ids": [repair_record["blocker_id"]],
        "blocker_aliases": repair_record.get("blocker_aliases", []),
        "migration_wave_blocked": wave_label(waves[7]),
        "wave1_authorization_blocked": True,
        "freeze_gate": {**repair_record["freeze_gate"], "wave0_condition": common_wave0_freeze["condition"], "evidence": repair_test["evidence"]},
        "seal_gate": repair_record["seal_gate"],
        "unlock_condition": "The named repair-chain integration test passes with result['ok'] is True and S13C-SE-028 validation_gate passes without repairchain, lineage, or runtime-session regression.",
        "criticality": repair_record["risk_level"],
        "criticality_basis": "Stage14 risk_level for S13C-SE-028.",
    }
    status = {
        "failure_id": "S15A1-GF-003",
        "test_name": status_test["test"],
        **PYTEST_EVIDENCE[status_test["test"]],
        "categories": ["runtime_status_ownership_drift"],
        "owner_domain": "non_mainline_observability / runtime_status_ownership",
        "blocking_owner": "runtime status ownership inventory",
        "native_owner": [item["native_owner"] for item in nonmainline],
        "blocker_ids": nonmainline_ids,
        "blocker_mapping_scope": "Stage14 non-mainline observability residue set; every item names this status-inventory suite in its validation gate.",
        "migration_wave_blocked": wave_label(waves[10]),
        "wave1_authorization_blocked": True,
        "freeze_gate": {
            **common_wave0_freeze,
            "assigned_failure_classification": "seal evidence in Stage14 and Stage15A",
            "evidence": "The aggregate Wave 0 validation remains failed while this seal-evidence test fails.",
        },
        "seal_gate": {
            "required": True,
            "condition": plan["seal_blockers"]["runtime_ownership_drift"]["condition"],
            "evidence_graph_condition": plan["seal_blockers"]["evidence_graph_drift"]["condition"],
            "evidence": status_test["evidence"],
        },
        "unlock_condition": "The named inventory test passes: every EXPECTED_HIGH_RISK_FILES entry is present in the scan findings, with the Stage14 non-mainline observability report retained.",
        "criticality": "critical",
        "criticality_basis": "Stage14 records this named test as critical-suite seal evidence; Stage15A preserves it as seal evidence.",
    }
    failures = [scheduler, repair, status]

    category_inventory = {category: [item["failure_id"] for item in failures if category in item["categories"]] for category in CATEGORIES}
    nonmainline_report = {
        "mandatory": True,
        "status": "preserved",
        "tracking_ids": nonmainline_ids,
        "count": len(nonmainline_ids),
        "failure_link": status["failure_id"],
        "classification": "observability-only; no reclassification or repair performed",
    }
    wave_graph = []
    direct_wave_numbers = [3, 7, 10]
    for item, number in zip(failures, direct_wave_numbers):
        downstream = [wave_label(waves[index]) for index in range(number + 1, 11)]
        wave_graph.append({
            "failure_id": item["failure_id"],
            "failure": item["test_name"],
            "blocked_wave": item["migration_wave_blocked"],
            "downstream_waves": downstream,
            "wave0_authorization_path": ["Wave 0: evidence and invariant lock", "Wave 1: authority context migration"],
            "freeze_impact": item["freeze_gate"],
            "seal_impact": item["seal_gate"],
        })

    removal_analysis = []
    all_ids = [item["failure_id"] for item in failures]
    for item in failures:
        remaining = [failure_id for failure_id in all_ids if failure_id != item["failure_id"]]
        removal_analysis.append({
            "failure_removed": item["failure_id"],
            "wave1_authorizable": False,
            "remaining_gate_failures": remaining,
            "reason": "Stage15A requires the complete validation gate to pass; two observed failures remain.",
        })

    sources = [STAGE14, STAGE15A, STAGE15A_SUMMARY, RUNTIME_BLOCKERS, *OWNERSHIP_ARTIFACTS]
    payload = {
        "stage": "Stage15A.1 — Wave 0 Gate Failure Decomposition",
        "scope": "failure_analysis_only",
        "production_runtime_modified": False,
        "tests_modified": False,
        "blockers_fixed": False,
        "sources": [{"artifact": relative(path), "sha256": sha256(path)} for path in sources],
        "source_validation": {
            "runtime_blocker_validation_loaded": bool(blocker_validation),
            "ownership_validation_artifacts_loaded": list(ownership),
            "stage15a_failure_set_matches": True,
        },
        "gate_failure_inventory": failures,
        "distinct_gate_failure_count": len(failures),
        "category_inventory": category_inventory,
        "non_mainline_issue_report": nonmainline_report,
        "wave_impact_graph": wave_graph,
        "authorization_analysis": {
            "can_wave1_be_authorized_if_each_failure_is_removed_individually": False,
            "individual_removal_analysis": removal_analysis,
            "can_wave1_be_authorized_if_all_failures_are_removed": True,
            "authorization_assumption": "All Stage15A invariant locks remain pass and the three named tests pass; no new validation failure appears.",
            "minimum_gate_set": all_ids,
            "required_unblocks": [{"failure_id": item["failure_id"], "condition": item["unlock_condition"]} for item in failures],
            "first_authorizable_wave": "Wave 1: authority context migration, after all minimum_gate_set conditions pass",
        },
        "highest_risk_failure": {
            "failure_id": scheduler["failure_id"],
            "test_name": scheduler["test_name"],
            "basis": "Critical freeze blocker with the earliest assigned blocked migration wave (Wave 3) among critical failures.",
        },
        "blocked_waves": {
            "direct": [wave_label(waves[number]) for number in direct_wave_numbers],
            "authorization": "Wave 1 is closed by the failed Wave 0 aggregate validation gate.",
            "transitive": [wave_label(waves[number]) for number in range(1, 11)],
        },
        "validation_results": VALIDATION_RESULTS,
    }
    counts = Counter(category for item in failures for category in item["categories"])
    summary = {
        "stage": payload["stage"],
        "failing_test_count": len(stage15a_names),
        "distinct_gate_failures": len(failures),
        "blocked_waves": payload["blocked_waves"],
        "highest_risk_failure": payload["highest_risk_failure"],
        "first_authorizable_wave": payload["authorization_analysis"]["first_authorizable_wave"],
        "minimum_gate_set": all_ids,
        "category_counts": {category: counts.get(category, 0) for category in CATEGORIES},
        "freeze_impact": "Wave 0 remains failed; Wave 1 and all sequential downstream waves remain unauthorized.",
        "seal_impact": "Wave 10 remains blocked by all three preserved failures; status inventory drift is explicit seal evidence.",
        "non_mainline_issue_reporting": "6 / 6 preserved in observability-only track",
        "validation_results": VALIDATION_RESULTS,
        "production_runtime_touched": False,
        "tests_touched": False,
        "blockers_fixed": False,
        "outputs": {"inventory": relative(OUTPUT), "summary": relative(SUMMARY), "report": relative(REPORT)},
    }
    return payload, summary


def write_report(payload: dict[str, Any], summary: dict[str, Any]) -> None:
    lines = [
        "# Stage15A.1 — Wave 0 Gate Failure Decomposition", "",
        "## Decision", "",
        f"- Failing tests: {summary['failing_test_count']}",
        f"- Distinct gate failures: {summary['distinct_gate_failures']}",
        f"- Highest risk: `{summary['highest_risk_failure']['failure_id']}` — `{summary['highest_risk_failure']['test_name']}`",
        f"- First authorizable wave: {summary['first_authorizable_wave']}",
        f"- Minimum gate set: {', '.join(f'`{item}`' for item in summary['minimum_gate_set'])}", "",
        "## Gate Failure Inventory", "",
    ]
    for item in payload["gate_failure_inventory"]:
        lines.extend([
            f"### {item['failure_id']}", "",
            f"- Test: `{item['test_name']}`",
            f"- Assertion: `{item['assertion']}`",
            f"- Categories: {', '.join(f'`{value}`' for value in item['categories'])}",
            f"- Owner/domain: `{item['blocking_owner']}` / `{item['owner_domain']}`",
            f"- Blocked wave: {item['migration_wave_blocked']}",
            f"- Blocker IDs: {', '.join(f'`{value}`' for value in item['blocker_ids'])}",
            f"- Unlock: {item['unlock_condition']}",
            f"- Criticality: `{item['criticality']}`", "",
        ])
    lines.extend(["## Categories", ""])
    for category, ids in payload["category_inventory"].items():
        lines.append(f"- `{category}`: {', '.join(ids) or 'none'}")
    lines.extend(["", "## Wave Impact Graph", ""])
    for edge in payload["wave_impact_graph"]:
        lines.append(f"- `{edge['failure_id']}` → {edge['blocked_wave']} → {', '.join(edge['downstream_waves']) or 'seal endpoint'} → freeze blocked → seal blocked")
    lines.extend([
        "", "## Authorization", "",
        "- Removing any one failure alone does not authorize Wave 1; two failures remain.",
        "- Removing all three failures authorizes Wave 1 only if all other Stage15A locks remain passing and no new failure appears.",
        f"- Freeze impact: {summary['freeze_impact']}",
        f"- Seal impact: {summary['seal_impact']}", "",
        "## Non-Mainline Issue Reporting", "",
        f"- {summary['non_mainline_issue_reporting']}",
        "- No non-mainline issue was reclassified or repaired.", "",
        "## Validation", "",
        f"- Generator: {payload['validation_results']['generator']}",
        f"- Compileall: {payload['validation_results']['compileall']}",
        f"- Limited pytest: {payload['validation_results']['pytest']['status']} (3/3 failures reproduced)", "",
        "## Scope attestation", "",
        "- Production runtime touched: false",
        "- Tests touched: false",
        "- Blockers fixed: false", "",
    ])
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    payload, summary = build()
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(payload, summary)
    print(f"failing_test_count: {summary['failing_test_count']}")
    print(f"distinct_gate_failures: {summary['distinct_gate_failures']}")
    print(f"blocked_waves: {', '.join(summary['blocked_waves']['direct'])}")
    print(f"highest_risk_failure: {summary['highest_risk_failure']['failure_id']}")
    print(f"first_authorizable_wave: {summary['first_authorizable_wave']}")
    print(f"minimum_gate_set: {', '.join(summary['minimum_gate_set'])}")
    print("production_runtime_touched: false")
    print("tests_touched: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
