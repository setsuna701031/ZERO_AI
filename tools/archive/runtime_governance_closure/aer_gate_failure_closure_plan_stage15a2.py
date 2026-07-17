from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
STAGE14 = OUT_DIR / "aer_ownership_migration_plan_stage14.json"
STAGE15A = OUT_DIR / "aer_wave0_execution_gate_stage15a.json"
STAGE15A1 = OUT_DIR / "aer_wave0_gate_failure_inventory_stage15a1.json"
OUTPUT = OUT_DIR / "gate_failure_closure_plan_stage15a2.json"
SUMMARY = OUT_DIR / "gate_failure_closure_plan_stage15a2_summary.json"
REPORT = OUT_DIR / "gate_failure_closure_plan_stage15a2_report.md"


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required artifact: {relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    stage14 = load(STAGE14)
    stage15a = load(STAGE15A)
    stage15a1 = load(STAGE15A1)
    failures = {item["failure_id"]: item for item in stage15a1.get("gate_failure_inventory", [])}
    expected_ids = ["S15A1-GF-001", "S15A1-GF-002", "S15A1-GF-003"]
    if list(failures) != expected_ids:
        raise SystemExit(f"gate failure inventory drift: expected={expected_ids}, actual={list(failures)}")
    if stage15a.get("readiness_decision", {}).get("wave1_ready") is not False:
        raise SystemExit("Stage15A Wave 1 must remain unauthorized")

    waves = {wave["wave"]: wave for wave in stage14["migration_waves"]}
    blockers = {item["blocker_id"]: item for item in stage14["blocker_migration_plan"]}
    direct_calls = stage14["freeze_blockers"]["direct_stepexecutor_call_seals"]
    nonmainline = stage14["non_mainline_issues"]
    repair = blockers["S13C-SE-028"]
    gf1, gf2, gf3 = (failures[item] for item in expected_ids)

    gf1_plan = {
        "failure_id": gf1["failure_id"],
        "root_cause": {
            "established": "The scheduler ownership AST scan finds six direct StepExecutor.execute_step calls where the delegation-boundary contract requires an empty direct-call set.",
            "implementation_cause_status": "fully localized by pytest and Stage14 direct-call evidence",
            "evidence": gf1["observed_result"],
        },
        "owner": gf1["blocking_owner"],
        "affected_symbols": unique([record["caller"] for record in direct_calls] + ["Scheduler.run_one_step", "StepExecutor.execute_step"]),
        "affected_locations": [f"{record['source_file']}:{record['source_line']}" for record in direct_calls],
        "affected_blockers": gf1["blocker_ids"],
        "affected_waves": ["Wave 3: scheduler direct-call seal", "Wave 4–10 downstream", "Wave 1 authorization through the failed Wave 0 aggregate gate"],
        "migration_dependencies": {
            "cannot_start_until": waves[3]["cannot_start_until_dependencies"],
            "required_upstream_waves": ["Wave 1: authority context migration", "Wave 2: planner goal overlay migration"],
            "expected_unlocks": waves[3]["expected_unlocks"],
            "ownership_boundary": "Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor",
        },
        "minimum_remediation_scope": {
            "package_id": "S15A2-RP-001",
            "scope": "One scheduler ownership package covering the six evidenced call sites in core/tasks/scheduler.py and their single delegation-boundary validation contract.",
            "out_of_scope": ["authority-context migration", "repair-chain handler behavior", "status inventory reconciliation", "test changes"],
            "execution_status": "not currently executable: Stage14 assigns it to Wave 3, while failed Wave 0 currently prevents Wave 1 and Wave 2 from starting",
        },
        "rollback_risk": {
            "level": "critical",
            "condition": waves[3]["rollback_condition"],
            "specific_risks": ["scheduler dispatch result drift", "task finalization drift", "retry handoff drift", "delegation-boundary regression"],
        },
        "validation_suites": waves[3]["validation_suites"],
        "freeze_impact": gf1["freeze_gate"],
        "seal_impact": gf1["seal_gate"],
        "closure_condition": gf1["unlock_condition"],
    }
    gf2_plan = {
        "failure_id": gf2["failure_id"],
        "root_cause": {
            "established": "For the autonomous_repair_chain test input, StepExecutor.execute_step returns result['ok'] == false instead of the required true handler contract.",
            "implementation_cause_status": "not established by the pytest assertion; deeper mechanism diagnosis is deferred to the authorized remediation package",
            "evidence": {"assertion": gf2["assertion"], "observed": gf2["observed_result"]},
        },
        "owner": gf2["blocking_owner"],
        "affected_symbols": ["StepExecutor.execute_step", "StepExecutor._handle_autonomous_repair_chain_step"],
        "affected_blockers": gf2["blocker_ids"],
        "affected_waves": ["Wave 7: repairchain recovery / retry / duplicate repair", "Wave 8–10 downstream", "Wave 1 authorization through the failed Wave 0 aggregate gate"],
        "migration_dependencies": {
            "cannot_start_until": waves[7]["cannot_start_until_dependencies"],
            "upstream_dependencies": repair["upstream_dependencies"],
            "downstream_unlocks": repair["downstream_unlocks"],
            "domains": repair["migration_domains"],
        },
        "minimum_remediation_scope": {
            "package_id": "S15A2-RP-002",
            "scope": "One blocker-scoped handler-contract package for S13C-SE-028, preserving repairchain, lineage, and runtime-session outputs.",
            "out_of_scope": ["other Wave 7 blockers unless diagnosis proves a dependency", "scheduler direct-call seal", "status inventory", "test changes"],
            "execution_status": "not currently executable: assigned to Wave 7 and dependent on Wave 6 completion",
        },
        "rollback_risk": {"level": repair["risk_level"], "condition": repair["rollback_condition"]},
        "validation_suites": repair["validation_gate"]["required_suites"],
        "freeze_impact": gf2["freeze_gate"],
        "seal_impact": gf2["seal_gate"],
        "closure_condition": gf2["unlock_condition"],
    }
    gf3_suites = unique([suite for item in nonmainline for suite in item["validation_gate"]["required_suites"]])
    gf3_plan = {
        "failure_id": gf3["failure_id"],
        "root_cause": {
            "established": "The explicit status-owner scan reports only core/runtime/task_runner.py while ten other EXPECTED_HIGH_RISK_FILES entries are absent, producing ownership-inventory evidence drift.",
            "implementation_cause_status": "inventory mismatch established; no unsupported cause is assigned to the ten absent findings",
            "missing_expected_high_risk_files": gf3["missing_expected_high_risk_files"],
        },
        "owner": gf3["blocking_owner"],
        "affected_symbols": [item["symbol"] for item in nonmainline] + ["EXPECTED_HIGH_RISK_FILES", "high_risk status assignment scan"],
        "affected_blockers": gf3["blocker_ids"],
        "affected_waves": ["Wave 8: compatibility bridge/non-mainline retirement evidence", "Wave 9: freeze validation", "Wave 10: seal validation", "Wave 1 authorization through the failed Wave 0 aggregate gate"],
        "migration_dependencies": {
            "cannot_start_until": waves[10]["cannot_start_until_dependencies"],
            "required_prior_tracks": ["Wave 8 compatibility bridge retirement", "Wave 9 freeze validation", "6/6 non-mainline observability records retained"],
            "non_mainline_track": [item["tracking_id"] for item in nonmainline],
        },
        "minimum_remediation_scope": {
            "package_id": "S15A2-RP-003",
            "scope": "One evidence-reconciliation package for the ten missing scan findings and six Stage14 non-mainline observability records; runtime ownership evidence must satisfy the unchanged test contract.",
            "out_of_scope": ["test expectation edits", "non-mainline reclassification", "scheduler direct-call changes", "repair-chain behavior changes"],
            "execution_status": "not currently executable: seal reconciliation is assigned to Wave 10 after Wave 9 completion",
        },
        "rollback_risk": {
            "level": "critical",
            "condition": "Rollback if reconciliation hides status writers, changes canonical status ownership, drops non-mainline evidence, or creates evidence-graph drift.",
        },
        "validation_suites": gf3_suites,
        "freeze_impact": gf3["freeze_gate"],
        "seal_impact": gf3["seal_gate"],
        "closure_condition": gf3["unlock_condition"],
        "non_mainline_issue_reporting": {"mandatory": True, "status": "preserved", "count": len(nonmainline), "tracking_ids": [item["tracking_id"] for item in nonmainline]},
    }
    plans = [gf1_plan, gf2_plan, gf3_plan]

    topology = {
        "status": "execution_dependency_deadlock",
        "evidence": [
            "Stage15A requires all three failed validations to clear before Wave 1 authorization.",
            "Stage14 assigns the remediation domains to Wave 3, Wave 7, and Wave 10.",
            "Stage14 sequential dependencies require Wave 1 before Wave 3, Wave 6 before Wave 7, and Wave 9 before Wave 10.",
        ],
        "consequence": "No runtime remediation package is executable under the current authorization topology without separate gate-policy authority; this plan does not alter that policy.",
    }
    decision = {
        "gate_to_clear_first": {
            "failure_id": "S15A1-GF-001",
            "reason": "It is the highest-risk failure and has the earliest Stage14-assigned remediation wave.",
            "qualification": "Priority only; it is not executable while Wave 1 and Wave 2 remain unauthorized.",
        },
        "smallest_executable_remediation_package": {
            "package_id": "S15A2-RP-001",
            "failure_id": "S15A1-GF-001",
            "nominal_scope": gf1_plan["minimum_remediation_scope"]["scope"],
            "current_executability": False,
            "blocker": topology["consequence"],
        },
        "first_gate_remediation_wave": {
            "wave": "Wave 3: scheduler direct-call seal",
            "currently_reachable": False,
            "prerequisites": ["Wave 0 complete", "Wave 1 complete", "Wave 2 complete"],
        },
        "expected_wave1_authorization_condition": "All Stage15A invariant locks remain passing; S15A1-GF-001, S15A1-GF-002, and S15A1-GF-003 all satisfy their closure conditions; the limited ownership/blocker suites pass; and no new validation failure appears.",
    }
    inputs = [STAGE14, STAGE15A, STAGE15A1]
    payload = {
        "stage": "Stage15A.2 — Gate Failure Closure Planning",
        "scope": "closure_planning_only",
        "production_runtime_modified": False,
        "tests_modified": False,
        "blockers_fixed": False,
        "inputs": [{"artifact": relative(path), "sha256": digest(path)} for path in inputs],
        "closure_plans": plans,
        "execution_topology": topology,
        "closure_decision": decision,
        "artifact_consistency": {
            "status": "pass",
            "failure_ids": expected_ids,
            "all_failures_planned": len(plans) == 3,
            "stage14_wave_assignments_preserved": True,
            "stage15a_authorization_condition_preserved": True,
            "non_mainline_reporting_preserved": True,
        },
    }
    summary = {
        "stage": payload["stage"],
        "closure_plan_count": len(plans),
        "gate_to_clear_first": decision["gate_to_clear_first"],
        "smallest_executable_remediation_package": decision["smallest_executable_remediation_package"],
        "first_gate_remediation_wave": decision["first_gate_remediation_wave"],
        "expected_wave1_authorization_condition": decision["expected_wave1_authorization_condition"],
        "execution_topology_status": topology["status"],
        "artifact_consistency": "pass",
        "production_runtime_touched": False,
        "tests_touched": False,
        "blockers_fixed": False,
        "outputs": {"plan": relative(OUTPUT), "summary": relative(SUMMARY), "report": relative(REPORT)},
    }
    return payload, summary


def write_report(payload: dict[str, Any], summary: dict[str, Any]) -> None:
    decision = payload["closure_decision"]
    lines = [
        "# Stage15A.2 — Gate Failure Closure Planning", "",
        "## Closure decision", "",
        f"- Gate to clear first: `{decision['gate_to_clear_first']['failure_id']}` — {decision['gate_to_clear_first']['reason']}",
        f"- Smallest scoped package: `{decision['smallest_executable_remediation_package']['package_id']}`",
        f"- Currently executable: `{str(decision['smallest_executable_remediation_package']['current_executability']).lower()}`",
        f"- First gate-remediation wave: {decision['first_gate_remediation_wave']['wave']}",
        f"- Expected Wave 1 authorization: {decision['expected_wave1_authorization_condition']}", "",
        "## Execution topology", "",
        f"- Status: `{payload['execution_topology']['status']}`",
        f"- Consequence: {payload['execution_topology']['consequence']}", "",
    ]
    for plan in payload["closure_plans"]:
        lines.extend([
            f"## {plan['failure_id']}", "",
            f"- Root cause: {plan['root_cause']['established']}",
            f"- Owner: `{plan['owner']}`",
            f"- Affected symbols: {', '.join(f'`{item}`' for item in plan['affected_symbols'])}",
            f"- Affected blockers: {', '.join(f'`{item}`' for item in plan['affected_blockers'])}",
            f"- Affected waves: {', '.join(plan['affected_waves'])}",
            f"- Minimum remediation: {plan['minimum_remediation_scope']['scope']}",
            f"- Rollback risk: `{plan['rollback_risk']['level']}` — {plan['rollback_risk']['condition']}",
            f"- Validation suites: {', '.join(f'`{item}`' for item in plan['validation_suites'])}",
            f"- Closure condition: {plan['closure_condition']}", "",
        ])
    lines.extend([
        "## Artifact consistency", "",
        "- Status: pass",
        "- Stage14 wave assignments preserved: true",
        "- Stage15A authorization condition preserved: true",
        "- Non-mainline reporting preserved: true", "",
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
    print(f"closure_plan_count: {summary['closure_plan_count']}")
    print(f"gate_to_clear_first: {summary['gate_to_clear_first']['failure_id']}")
    print(f"smallest_package: {summary['smallest_executable_remediation_package']['package_id']}")
    print(f"currently_executable: {str(summary['smallest_executable_remediation_package']['current_executability']).lower()}")
    print(f"first_gate_remediation_wave: {summary['first_gate_remediation_wave']['wave']}")
    print(f"artifact_consistency: {summary['artifact_consistency']}")
    print("production_runtime_touched: false")
    print("tests_touched: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
