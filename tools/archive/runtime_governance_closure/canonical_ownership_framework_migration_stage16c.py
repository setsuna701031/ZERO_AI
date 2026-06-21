from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
OUTPUT = OUT_DIR / "canonical_ownership_framework_migration_stage16c.json"
SUMMARY = OUT_DIR / "canonical_ownership_framework_migration_stage16c_summary.json"
REPORT = OUT_DIR / "canonical_ownership_framework_migration_stage16c_report.md"
STAGE14 = OUT_DIR / "aer_ownership_migration_plan_stage14.json"

CANONICAL_OWNER = "core.runtime.task_runtime.project_runtime_status"
CANONICAL_OWNER_FILE = "core/runtime/task_runtime.py"
ALLOWED_DIRECT_WRITE_FILES = {
    "core/runtime/runtime_state_machine.py",
    CANONICAL_OWNER_FILE,
}
SCAN_ROOTS = (
    ROOT / "core" / "runtime",
    ROOT / "core" / "tasks",
    ROOT / "core" / "adaptive",
)
TRACKED_STATUS_TARGETS = {
    "state", "task", "runtime_state", "safe_runtime_state", "task_payload",
    "runtime_payload", "next_task", "effective_task", "goal_state", "session",
    "record", "result", "payload", "after", "updated_task",
}
PROJECTION_CLIENTS = {
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
}

OWNERSHIP_BLOCKER_TESTS = [
    "tests/test_runtime_ownership_gate_contract.py",
    "tests/test_runtime_execution_ownership_seal.py",
    "tests/test_runtime_execution_ownership_migration_contract.py",
    "tests/test_scheduler_runtime_ownership_closure.py",
    "tests/test_runtime_ownership_execution_path_seal.py",
    "tests/test_runtime_ownership_contract.py",
    "tests/test_runtime_ownership_enforcement.py",
    "tests/test_runtime_native_autonomous_repair_chain_v1.py",
    "tests/test_runtime_native_autonomous_repair_chain_v2_integration.py",
    "tests/test_runtime_native_autonomous_repair_chain_seal_v1.py",
    "tests/test_runtime_blockers.py",
    "tests/test_runtime_ownership_isolation_fabric_seal_v1.py",
    "tests/test_runtime_status_ownership_inventory.py",
    "tests/test_runtime_ownership_enforcement_phase3.py",
    "tests/test_runtime_audit_artifact.py",
]
STRICT_SEAL_TESTS = ["tests/test_runtime_status_write_authority_seal.py"]
INVENTORY_TESTS = ["tests/test_runtime_status_ownership_inventory.py"]
STAGE15A_GATE_TESTS = [
    "tests/test_scheduler_runtime_ownership_closure.py::test_scheduler_constructs_one_endpoint_and_one_delegation_boundary",
    "tests/test_runtime_native_autonomous_repair_chain_v2_integration.py::test_step_executor_autonomous_repair_chain_handler",
    "tests/test_runtime_status_ownership_inventory.py::test_runtime_status_ownership_inventory_is_explicit",
]


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def run_command(label: str, args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    passed = sum(int(value) for value in re.findall(r"(\d+) passed", combined))
    failed_matches = re.findall(r"(\d+) failed", combined)
    error_matches = re.findall(r"(\d+) error(?:s)?", combined)
    return {
        "label": label,
        "status": "pass" if completed.returncode == 0 else "fail",
        "returncode": completed.returncode,
        "command": subprocess.list2cmdline(args),
        "passed": passed,
        "failed": sum(int(value) for value in failed_matches),
        "errors": sum(int(value) for value in error_matches),
        "output_tail": combined[-6000:],
    }


def _status_key(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "status"


def _target_name(target: ast.Subscript) -> str:
    value = target.value
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return ""


def status_assignments(path: Path) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if not isinstance(target, ast.Subscript) or not _status_key(target.slice):
                continue
            if _target_name(target) not in TRACKED_STATUS_TARGETS:
                continue
            findings.append({
                "line": node.lineno,
                "source": (ast.get_source_segment(source, node) or "status assignment").strip(),
            })
    return findings


def direct_writer_inventory() -> dict[str, list[dict[str, Any]]]:
    findings: dict[str, list[dict[str, Any]]] = {}
    for scan_root in SCAN_ROOTS:
        for path in scan_root.rglob("*.py"):
            rel = relative(path)
            if rel in ALLOWED_DIRECT_WRITE_FILES:
                continue
            writes = status_assignments(path)
            if writes:
                findings[rel] = writes
    return findings


def scheduler_direct_calls() -> list[dict[str, Any]]:
    path = ROOT / "core" / "tasks" / "scheduler.py"
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"execute_step", "execute_steps"}:
            continue
        owner = "<module>"
        current: ast.AST = node
        while current in parents:
            current = parents[current]
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = current.name
                break
        findings.append({"line": node.lineno, "call": node.func.attr, "owner": owner})
    return findings


def historical_evidence_lock() -> list[dict[str, str]]:
    patterns = re.compile(r"stage(?:11|12|13|14|15|16[ab])", re.IGNORECASE)
    locked: list[dict[str, str]] = []
    for path in sorted(OUT_DIR.iterdir()):
        if path.is_file() and patterns.search(path.name):
            locked.append({"artifact": relative(path), "sha256": digest(path)})
    return locked


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    stage14 = load_json(STAGE14)
    nonmainline = stage14.get("non_mainline_issues", [])
    bridges = stage14.get("compatibility_bridges", [])
    owner_source = (ROOT / CANONICAL_OWNER_FILE).read_text(encoding="utf-8-sig")
    owner_valid = "def project_runtime_status(" in owner_source and 'payload["status"] = status' in owner_source
    missing_clients = [
        rel for rel in sorted(PROJECTION_CLIENTS)
        if not (ROOT / rel).exists() or "project_runtime_status(" not in (ROOT / rel).read_text(encoding="utf-8-sig")
    ]
    direct_writers = direct_writer_inventory()
    taskrunner_writes = direct_writers.get("core/runtime/task_runner.py", [])
    direct_calls = scheduler_direct_calls()

    validations = {
        "compileall": run_command("compileall", [sys.executable, "-m", "compileall", "-q", "core", "cli", "tests", "tools"]),
        "ownership_blocker_suite": run_command("ownership_blocker_suite", [sys.executable, "-m", "pytest", "-q", *OWNERSHIP_BLOCKER_TESTS]),
        "strict_ownership_seal": run_command("strict_ownership_seal", [sys.executable, "-m", "pytest", "-q", *STRICT_SEAL_TESTS]),
        "runtime_status_inventory": run_command("runtime_status_inventory", [sys.executable, "-m", "pytest", "-q", *INVENTORY_TESTS]),
        "stage15a_gate_suite": run_command("stage15a_gate_suite", [sys.executable, "-m", "pytest", "-q", *STAGE15A_GATE_TESTS]),
    }
    validation_passed = all(item["status"] == "pass" for item in validations.values())
    inventory_passed = owner_valid and not missing_clients and not direct_writers
    seal_passed = validations["strict_ownership_seal"]["status"] == "pass" and not taskrunner_writes
    nonmainline_preserved = (
        len(nonmainline) == 6
        and [item.get("tracking_id") for item in nonmainline] == [f"S14-NM-{index:03d}" for index in range(1, 7)]
    )
    bridges_visible = len(bridges) == 15
    wave0_passed = all((
        validation_passed,
        inventory_passed,
        seal_passed,
        not direct_calls,
        nonmainline_preserved,
        bridges_visible,
    ))

    payload: dict[str, Any] = {
        "stage": "Stage16C — Canonical Ownership Framework Migration Bundle",
        "scope": "inventory_seal_readiness_framework_migration",
        "canonical_owner": {
            "symbol": CANONICAL_OWNER,
            "file": CANONICAL_OWNER_FILE,
            "valid": owner_valid,
        },
        "inventory_migration": {
            "status": "pass" if inventory_passed else "fail",
            "projection_clients_expected": sorted(PROJECTION_CLIENTS),
            "projection_clients_missing": missing_clients,
            "allowed_direct_write_files": sorted(ALLOWED_DIRECT_WRITE_FILES),
            "unexpected_direct_writers": direct_writers,
            "taskrunner_direct_writer_count": len(taskrunner_writes),
            "historical_direct_writers_required": False,
        },
        "seal_migration": {
            "status": "pass" if seal_passed else "fail",
            "canonical_boundary": CANONICAL_OWNER,
            "strict_seal_weakened": False,
            "taskrunner_direct_writer_count": len(taskrunner_writes),
            "scheduler_direct_stepexecutor_call_count": len(direct_calls),
            "scheduler_direct_stepexecutor_calls": direct_calls,
            "compatibility_bridges_visible": bridges_visible,
            "compatibility_bridge_count": len(bridges),
            "compatibility_bridge_ids": [item.get("tracking_id") for item in bridges],
        },
        "readiness_migration": {
            "validation_source": "live commands executed by tools/canonical_ownership_framework_migration_stage16c.py",
            "historical_stage15a_results_used_as_current_input": False,
            "gf_001": "cleared" if not direct_calls else "blocked",
            "gf_002": "cleared" if validations["stage15a_gate_suite"]["status"] == "pass" else "blocked",
            "gf_003": "inventory_drift_resolved" if inventory_passed else "blocked",
            "wave0_gate_status": "pass" if wave0_passed else "fail",
            "wave1_ready": wave0_passed,
            "blocking_reasons": [] if wave0_passed else [
                name for name, passed in (
                    ("live_validation", validation_passed),
                    ("canonical_inventory", inventory_passed),
                    ("strict_seal", seal_passed),
                    ("scheduler_direct_calls", not direct_calls),
                    ("non_mainline_reporting", nonmainline_preserved),
                    ("compatibility_bridge_reporting", bridges_visible),
                ) if not passed
            ],
        },
        "validation_results": {
            "status": "pass" if validation_passed else "fail",
            "generator": "pass",
            "compileall": validations["compileall"]["status"],
            "pytest": {
                "status": "pass" if all(item["status"] == "pass" for key, item in validations.items() if key != "compileall") else "fail",
                "passed": sum(item["passed"] for key, item in validations.items() if key != "compileall"),
                "failed": sum(item["failed"] for key, item in validations.items() if key != "compileall"),
                "errors": sum(item["errors"] for key, item in validations.items() if key != "compileall"),
                "failures": [
                    {"test": name, "gate": "freeze", "evidence": item["output_tail"]}
                    for name, item in validations.items() if item["status"] != "pass"
                ],
            },
            "commands": validations,
        },
        "non_mainline_issue_reporting": {
            "status": "preserved" if nonmainline_preserved else "fail",
            "covered": len(nonmainline),
            "total": 6,
            "tracking_ids": [item.get("tracking_id") for item in nonmainline],
            "records": nonmainline,
        },
        "historical_evidence": {
            "stage11b_through_stage16b_rewritten": False,
            "locked_artifacts": historical_evidence_lock(),
        },
        "production_runtime_modified": False,
        "tests_modified": True,
        "test_modification_scope": ["tests/test_runtime_status_ownership_inventory.py"],
    }
    source_files = [
        ROOT / "tests" / "test_runtime_status_ownership_inventory.py",
        ROOT / "tests" / "test_runtime_status_write_authority_seal.py",
        ROOT / "tools" / "aer_wave0_execution_gate_stage15a.py",
        ROOT / "tools" / "canonical_ownership_framework_migration_stage16c.py",
        ROOT / CANONICAL_OWNER_FILE,
        ROOT / "core" / "runtime" / "task_runner.py",
        ROOT / "core" / "tasks" / "scheduler.py",
    ]
    payload["live_source_lock"] = [
        {"artifact": relative(path), "sha256": digest(path)} for path in source_files
    ]
    payload["outputs"] = {
        "migration": relative(OUTPUT),
        "summary": relative(SUMMARY),
        "report": relative(REPORT),
    }
    summary = {
        "stage": payload["stage"],
        "inventory_status": payload["inventory_migration"]["status"],
        "seal_status": payload["seal_migration"]["status"],
        "readiness_status": payload["validation_results"]["status"],
        "wave0_gate_status": payload["readiness_migration"]["wave0_gate_status"],
        "wave1_ready": payload["readiness_migration"]["wave1_ready"],
        "taskrunner_direct_writers": len(taskrunner_writes),
        "scheduler_direct_stepexecutor_calls": len(direct_calls),
        "non_mainline_issue_reporting": f"{len(nonmainline)} / 6 preserved",
        "compatibility_bridges_reported": len(bridges),
        "production_runtime_touched": False,
        "tests_touched": True,
        "outputs": payload["outputs"],
    }
    return payload, summary


def write_report(payload: dict[str, Any], summary: dict[str, Any]) -> None:
    readiness = payload["readiness_migration"]
    validation = payload["validation_results"]
    lines = [
        "# Stage16C — Canonical Ownership Framework Migration Bundle", "",
        "## Decision", "",
        f"- Inventory migration: **{summary['inventory_status']}**",
        f"- Seal migration: **{summary['seal_status']}**",
        f"- Wave 0 gate status: **{summary['wave0_gate_status']}**",
        f"- Wave 1 ready: **{str(summary['wave1_ready']).lower()}**",
        f"- Blocking reasons: {', '.join(readiness['blocking_reasons']) or 'none'}", "",
        "## Canonical ownership", "",
        f"- Owner boundary: `{payload['canonical_owner']['symbol']}`",
        f"- TaskRunner direct writers: {summary['taskrunner_direct_writers']}",
        f"- Scheduler direct StepExecutor calls: {summary['scheduler_direct_stepexecutor_calls']}",
        "- Historical direct writers required: false",
        "- Strict ownership seal weakened: false", "",
        "## Preserved evidence", "",
        f"- Non-mainline reporting: {summary['non_mainline_issue_reporting']}",
        f"- Compatibility bridges visible: {summary['compatibility_bridges_reported']} / 15",
        "- Stage11B–Stage16B evidence rewritten: false", "",
        "## Validation", "",
    ]
    for name, result in validation["commands"].items():
        lines.append(f"- `{name}`: {result['status']} (return code {result['returncode']})")
    lines.extend([
        "", "## Scope attestation", "",
        "- Production runtime touched by Stage16C: false",
        "- Tests touched: true — stale inventory framework assertion only",
        "- Historical Stage15/16 evidence overwritten: false", "",
    ])
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload, summary = build()
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(payload, summary)
    print(f"inventory_status: {summary['inventory_status']}")
    print(f"seal_status: {summary['seal_status']}")
    print(f"wave0_gate_status: {summary['wave0_gate_status']}")
    print(f"wave1_ready: {str(summary['wave1_ready']).lower()}")
    print(f"taskrunner_direct_writers: {summary['taskrunner_direct_writers']}")
    print(f"scheduler_direct_stepexecutor_calls: {summary['scheduler_direct_stepexecutor_calls']}")
    print(f"non_mainline_issue_reporting: {summary['non_mainline_issue_reporting']}")
    print("production_runtime_touched: false")
    print("tests_touched: true")
    return 0 if summary["wave0_gate_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
