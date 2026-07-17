from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
PLAN = OUT_DIR / "aer_ownership_migration_plan_stage14.json"
PLAN_SUMMARY = OUT_DIR / "aer_ownership_migration_plan_stage14_summary.json"
PLAN_REPORT = OUT_DIR / "aer_ownership_migration_plan_stage14_report.md"
HISTORICAL_OUTPUT = OUT_DIR / "aer_wave0_execution_gate_stage15a.json"
HISTORICAL_SUMMARY = OUT_DIR / "aer_wave0_execution_gate_stage15a_summary.json"
HISTORICAL_REPORT = OUT_DIR / "aer_wave0_execution_gate_stage15a_report.md"
LIVE_VALIDATION = OUT_DIR / "canonical_ownership_framework_migration_stage16c.json"
OUTPUT = OUT_DIR / "aer_wave0_execution_gate_stage16c.json"
SUMMARY = OUT_DIR / "aer_wave0_execution_gate_stage16c_summary.json"
REPORT = OUT_DIR / "aer_wave0_execution_gate_stage16c_report.md"

EXPECTED_WAVES = [
    "evidence and invariant lock",
    "authority context migration",
    "planner goal overlay migration",
    "scheduler direct-call seal",
    "taskrunner execution ownership",
    "stepexecutor fallback / execution ownership",
    "lineage + runtime-session boundary",
    "repairchain recovery / retry / duplicate repair",
    "compatibility bridge retirement",
    "freeze validation",
    "seal validation",
]

def load_live_validation() -> tuple[dict[str, Any], dict[str, Any]]:
    live = load_object(LIVE_VALIDATION)
    source_lock = live.get("live_source_lock")
    if not isinstance(source_lock, list) or not source_lock:
        raise SystemExit(f"missing live source lock: {relative(LIVE_VALIDATION)}")
    stale: list[str] = []
    for item in source_lock:
        path = ROOT / str(item.get("artifact") or "")
        if not path.is_file() or digest(path) != item.get("sha256"):
            stale.append(str(item.get("artifact") or "<missing>"))
    if stale:
        raise SystemExit(f"live validation source lock is stale: {stale}")
    validation = live.get("validation_results")
    if not isinstance(validation, dict):
        raise SystemExit(f"missing live validation_results: {relative(LIVE_VALIDATION)}")
    return live, validation


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required Stage14 artifact: {relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(checks: list[dict[str, Any]], name: str, passed: bool, expected: Any, actual: Any, gate: str) -> None:
    checks.append({
        "check": name,
        "status": "pass" if passed else "fail",
        "gate": gate,
        "expected": expected,
        "actual": actual,
    })


def populated(item: dict[str, Any], field: str) -> bool:
    return field in item and item[field] not in (None, "", [], {})


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    plan = load_object(PLAN)
    plan_summary = load_object(PLAN_SUMMARY)
    live, validation_results = load_live_validation()
    if not PLAN_REPORT.exists():
        raise SystemExit(f"missing required Stage14 artifact: {relative(PLAN_REPORT)}")

    blockers = plan.get("blocker_migration_plan", [])
    waves = plan.get("migration_waves", [])
    freeze_ids = plan.get("freeze_blockers", {}).get("all_confirmed_blockers", [])
    seal_ids = plan.get("seal_blockers", {}).get("all_actionable_records", [])
    bridges = plan.get("compatibility_bridges", [])
    nonmainline = plan.get("non_mainline_issues", [])
    historical_direct_calls = plan.get("freeze_blockers", {}).get("direct_stepexecutor_call_seals", [])
    current_direct_call_count = int(live.get("seal_migration", {}).get("scheduler_direct_stepexecutor_call_count", -1))
    current_taskrunner_writer_count = int(live.get("inventory_migration", {}).get("taskrunner_direct_writer_count", -1))
    wave_by_number = {wave.get("wave"): wave for wave in waves}
    blocker_ids = [item.get("blocker_id") for item in blockers]
    bridge_ids = [item.get("tracking_id") for item in bridges]
    nonmainline_ids = [item.get("tracking_id") for item in nonmainline]
    checks: list[dict[str, Any]] = []

    check(checks, "confirmed_blockers_planned", len(blockers) == 113 and plan.get("total_confirmed_blockers_planned") == 113, 113, len(blockers), "freeze")
    check(checks, "freeze_blockers_present", len(freeze_ids) == 113 and set(freeze_ids) == set(blocker_ids), 113, len(freeze_ids), "freeze")
    check(checks, "seal_blockers_present", len(seal_ids) == 134 and set(seal_ids) == set(blocker_ids + bridge_ids + nonmainline_ids), 134, len(seal_ids), "seal")
    check(checks, "migration_waves_present", len(waves) == 11, 11, len(waves), "freeze")
    check(checks, "wave_order_preserved", [wave.get("name") for wave in waves] == EXPECTED_WAVES and [wave.get("wave") for wave in waves] == list(range(11)), EXPECTED_WAVES, [wave.get("name") for wave in waves], "freeze")
    check(checks, "wave_0_exists", 0 in wave_by_number, True, 0 in wave_by_number, "freeze")
    check(checks, "wave_1_exists", 1 in wave_by_number, True, 1 in wave_by_number, "freeze")
    check(checks, "wave_1_authority_context", wave_by_number.get(1, {}).get("name") == "authority context migration", "authority context migration", wave_by_number.get(1, {}).get("name"), "freeze")
    check(checks, "production_runtime_untouched", plan.get("production_runtime_modified") is False and plan_summary.get("production_runtime_touched") is False, False, plan.get("production_runtime_modified"), "freeze")
    check(checks, "tests_untouched", plan.get("tests_modified") is False and plan_summary.get("tests_touched") is False, False, plan.get("tests_modified"), "freeze")

    field_aliases = {
        "blocker_id": "blocker_id",
        "native_owner": "native_owner",
        "migration_wave": "primary_migration_wave",
        "safe_removal_precondition": "safe_removal_precondition",
        "validation_gate": "validation_gate",
        "rollback_condition": "rollback_condition",
        "freeze_gate": "freeze_gate",
        "seal_gate": "seal_gate",
    }
    field_coverage: dict[str, Any] = {}
    for required_name, source_name in field_aliases.items():
        covered = [item.get("blocker_id") for item in blockers if populated(item, source_name)]
        missing = [item.get("blocker_id") or f"index:{index}" for index, item in enumerate(blockers) if not populated(item, source_name)]
        field_coverage[required_name] = {"source_field": source_name, "covered": len(covered), "total": len(blockers), "missing": missing}
        check(checks, f"blocker_field_{required_name}", len(covered) == 113, 113, len(covered), "freeze" if required_name != "seal_gate" else "seal")

    wave0 = wave_by_number.get(0, {})
    wave1 = wave_by_number.get(1, {})
    check(checks, "wave_0_completion_criteria_exists", populated(wave0, "completion_criteria"), True, populated(wave0, "completion_criteria"), "freeze")
    wave1_dependencies = wave1.get("cannot_start_until_dependencies", [])
    check(checks, "wave_1_requires_wave_0", "wave_0_complete" in wave1_dependencies, "wave_0_complete", wave1_dependencies, "freeze")
    authority_ids = [item["blocker_id"] for item in blockers if "authority_context" in item.get("migration_domains", [])]
    wave1_ids = wave1.get("included_blockers", [])
    check(checks, "wave_1_contains_authority_context_blockers", bool(authority_ids) and set(authority_ids).issubset(set(wave1_ids)), authority_ids, wave1_ids, "freeze")
    sequential = all(
        f"wave_{number - 1}_complete" in wave_by_number.get(number, {}).get("cannot_start_until_dependencies", [])
        for number in range(2, 11)
    )
    check(checks, "later_wave_dependencies_preserve_order", sequential, True, sequential, "freeze")

    wave3 = wave_by_number.get(3, {})
    historical_direct_calls_locked = (
        len(historical_direct_calls) == 6
        and wave3.get("name") == "scheduler direct-call seal"
        and "wave_2_complete" in wave3.get("cannot_start_until_dependencies", [])
    )
    check(checks, "historical_direct_stepexecutor_evidence_preserved", historical_direct_calls_locked, 6, len(historical_direct_calls), "seal")
    check(checks, "live_direct_stepexecutor_calls_cleared", current_direct_call_count == 0, 0, current_direct_call_count, "seal")
    check(checks, "live_taskrunner_direct_status_writers_cleared", current_taskrunner_writer_count == 0, 0, current_taskrunner_writer_count, "seal")

    wave8_ids = set(wave_by_number.get(8, {}).get("included_blockers", []))
    bridges_retirement_only = all(
        item.get("validated_classification") == "compatibility_bridge"
        and item.get("migration_domain") == "compatibility_bridge"
        and item.get("tracking_id") in wave8_ids
        and "Retire only after" in item.get("migration_action", "")
        for item in bridges
    ) and len(bridges) == 15
    check(checks, "compatibility_bridges_retirement_only", bridges_retirement_only, 15, len(bridges), "seal")

    waves_before_seal = {item for wave in waves[:10] for item in wave.get("included_blockers", [])}
    nonmainline_observability_only = all(
        item.get("validated_classification") == "non_mainline_issue"
        and item.get("migration_domain") == "non_mainline_observability"
        and item.get("tracking_id") not in waves_before_seal
        for item in nonmainline
    ) and len(nonmainline) == 6
    check(checks, "non_mainline_issues_observability_only", nonmainline_observability_only, 6, len(nonmainline), "seal")

    evidence_paths = [PLAN, PLAN_SUMMARY, PLAN_REPORT, HISTORICAL_OUTPUT, HISTORICAL_SUMMARY, HISTORICAL_REPORT]
    for item in plan.get("inputs", []):
        path = ROOT / item
        if path.exists() and path not in evidence_paths:
            evidence_paths.append(path)
    evidence_lock = [{"artifact": relative(path), "sha256": digest(path), "exists": True} for path in evidence_paths]

    validation_passed = (
        validation_results.get("generator") == "pass"
        and validation_results.get("compileall") == "pass"
        and validation_results.get("pytest", {}).get("status") == "pass"
    )
    check(checks, "stage15a_live_validation", validation_passed, "pass", validation_results.get("status"), "freeze")
    for failure in validation_results.get("pytest", {}).get("failures", []):
        check(
            checks,
            f"validation::{failure['test']}",
            False,
            "pass",
            failure.get("evidence", "validation failure recorded as gate evidence"),
            failure.get("gate", "freeze"),
        )
    failed = [item for item in checks if item["status"] == "fail"]
    freeze_evidence = [item for item in failed if item["gate"] == "freeze"]
    seal_evidence = [item for item in failed if item["gate"] == "seal"]
    wave0_gate_status = "pass" if not failed else "fail"
    wave1_ready = wave0_gate_status == "pass"

    payload = {
        "stage": "Stage15A successor — Stage16C Live AER Wave 0 Gate",
        "scope": "live_validation_and_historical_evidence_lock",
        "source_of_truth": relative(PLAN),
        "live_validation_source": relative(LIVE_VALIDATION),
        "production_runtime_modified": False,
        "tests_modified": True,
        "blockers_fixed": False,
        "evidence_lock": evidence_lock,
        "invariant_checks": checks,
        "blocker_coverage": {
            "covered": len(blockers) - len([item for item in blockers if not all(populated(item, field) for field in field_aliases.values())]),
            "total": len(blockers),
            "field_coverage": field_coverage,
        },
        "freeze_blocker_coverage": {"covered": len(set(freeze_ids) & set(blocker_ids)), "total": len(blocker_ids), "exact_set_match": set(freeze_ids) == set(blocker_ids)},
        "seal_blocker_coverage": {"covered": len(set(seal_ids) & set(blocker_ids + bridge_ids + nonmainline_ids)), "total": len(blocker_ids + bridge_ids + nonmainline_ids), "exact_set_match": set(seal_ids) == set(blocker_ids + bridge_ids + nonmainline_ids)},
        "compatibility_bridge_coverage": {"covered": len(bridges), "total": 15, "track": "bridge_retirement", "retirement_only": bridges_retirement_only, "tracking_ids": bridge_ids},
        "non_mainline_issue_coverage": {"covered": len(nonmainline), "total": 6, "track": "observability", "observability_only": nonmainline_observability_only, "tracking_ids": nonmainline_ids},
        "direct_stepexecutor_call_seals": {
            "current_count": current_direct_call_count,
            "status": "pass" if current_direct_call_count == 0 else "fail",
            "historical_count": len(historical_direct_calls),
            "historical_records": historical_direct_calls,
        },
        "wave_gate": {
            "wave_0_completion_criteria": wave0.get("completion_criteria"),
            "wave_1_cannot_start_until": wave1_dependencies,
            "ordered_waves": [{"wave": item.get("wave"), "name": item.get("name")} for item in waves],
        },
        "readiness_decision": {
            "wave0_gate_status": wave0_gate_status,
            "wave1_ready": wave1_ready,
            "blocking_reasons": [item["check"] for item in failed],
            "freeze_evidence": freeze_evidence,
            "seal_evidence": seal_evidence,
            "first_executable_wave": "Wave 1: authority context migration" if wave1_ready else "none; Wave 1 remains gated by Wave 0",
        },
        "validation_results": validation_results,
    }
    summary = {
        "stage": payload["stage"],
        "wave0_gate_status": wave0_gate_status,
        "wave1_ready": wave1_ready,
        "confirmed_blocker_coverage": f"{payload['blocker_coverage']['covered']} / {len(blockers)}",
        "freeze_blocker_coverage": f"{payload['freeze_blocker_coverage']['covered']} / {len(blocker_ids)}",
        "seal_blocker_coverage": f"{payload['seal_blocker_coverage']['covered']} / {len(blocker_ids + bridge_ids + nonmainline_ids)}",
        "compatibility_bridge_coverage": f"{len(bridges)} / 15 retirement-only",
        "non_mainline_issue_coverage": f"{len(nonmainline)} / 6 observability-only",
        "direct_stepexecutor_call_seal_status": payload["direct_stepexecutor_call_seals"]["status"],
        "blocking_reasons": payload["readiness_decision"]["blocking_reasons"],
        "freeze_evidence_count": len(freeze_evidence),
        "seal_evidence_count": len(seal_evidence),
        "first_executable_wave": payload["readiness_decision"]["first_executable_wave"],
        "validation_results": validation_results,
        "production_runtime_touched": False,
        "tests_touched": True,
        "blockers_fixed": False,
        "deterministic_output": False,
        "live_source_lock_verified": True,
        "outputs": {"gate": relative(OUTPUT), "summary": relative(SUMMARY), "report": relative(REPORT)},
    }
    return payload, summary


def write_report(payload: dict[str, Any], summary: dict[str, Any]) -> None:
    decision = payload["readiness_decision"]
    validation = payload["validation_results"]
    lines = [
        "# Stage15A successor — Stage16C Live AER Wave 0 Gate", "",
        "## Readiness decision", "",
        f"- Wave 0 gate status: **{decision['wave0_gate_status']}**",
        f"- Wave 1 ready: **{str(decision['wave1_ready']).lower()}**",
        f"- First executable wave: {decision['first_executable_wave']}",
        f"- Blocking reasons: {', '.join(decision['blocking_reasons']) or 'none'}", "",
        "## Coverage locks", "",
        f"- Confirmed blockers: {summary['confirmed_blocker_coverage']}",
        f"- Freeze blockers: {summary['freeze_blocker_coverage']}",
        f"- Seal blockers: {summary['seal_blocker_coverage']}",
        f"- Compatibility bridges: {summary['compatibility_bridge_coverage']}",
        f"- Non-mainline issues: {summary['non_mainline_issue_coverage']}",
        f"- Live direct StepExecutor calls: {payload['direct_stepexecutor_call_seals']['current_count']}; {payload['direct_stepexecutor_call_seals']['status']}",
        f"- Historical direct-call evidence retained: {payload['direct_stepexecutor_call_seals']['historical_count']} records", "",
        "## Gate evidence", "",
    ]
    for item in payload["invariant_checks"]:
        lines.append(f"- `{item['status']}` — `{item['check']}` (gate: `{item['gate']}`)")
    lines.extend([
        "", "## Validation", "",
        f"- Generator: {validation['generator']}",
        f"- Compileall: {validation['compileall']}",
        f"- Pytest: {validation['pytest']['status']} ({validation['pytest']['passed']} passed, {validation['pytest']['failed']} failed, {validation['pytest']['errors']} errors)",
        f"- Overall: {validation['status']}",
        "- Any failure is retained as freeze/seal evidence; no blocker, runtime, or test repair is performed.", "",
        "## Scope attestation", "",
        "- Production runtime touched: false",
        "- Tests touched: true — stale inventory assertion only",
        "- Blockers fixed: false", "",
    ])
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    payload, summary = build()
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(payload, summary)
    print(f"wave0_gate_status: {summary['wave0_gate_status']}")
    print(f"wave1_ready: {str(summary['wave1_ready']).lower()}")
    print(f"confirmed_blocker_coverage: {summary['confirmed_blocker_coverage']}")
    print(f"freeze_blocker_coverage: {summary['freeze_blocker_coverage']}")
    print(f"seal_blocker_coverage: {summary['seal_blocker_coverage']}")
    print(f"compatibility_bridge_coverage: {summary['compatibility_bridge_coverage']}")
    print(f"non_mainline_issue_coverage: {summary['non_mainline_issue_coverage']}")
    print(f"direct_stepexecutor_call_seal_status: {summary['direct_stepexecutor_call_seal_status']}")
    print("production_runtime_touched: false")
    print("tests_touched: true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
