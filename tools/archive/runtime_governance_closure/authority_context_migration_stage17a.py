from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
INVENTORY = OUT_DIR / "authority_context_migration_stage17a_inventory.json"
VALIDATION = OUT_DIR / "authority_context_migration_stage17a_validation.json"
REPORT = OUT_DIR / "authority_context_migration_stage17a_report.md"
STAGE14 = OUT_DIR / "aer_ownership_migration_plan_stage14.json"

OWNERSHIP_TESTS = [
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
AUTHORITY_TESTS = [
    "tests/test_taskrunner_authority_context_canonical_migration.py",
    "tests/test_scheduler_taskrunner_authority_propagation_contract.py",
    "tests/test_scheduler_no_direct_mutation_contract.py",
    "tests/test_taskrunner_document_authority_metadata.py",
    "tests/test_step_executor_side_effect_pre_authority_contract.py",
    "tests/test_runtime_execution_authority_closure.py",
    "tests/test_runtime_execution_authority_seal.py",
    "tests/test_runtime_capability_dispatcher_contract.py",
    "tests/test_runtime_capability_propagation_closure.py",
    "tests/test_runtime_authority_seal_contract.py",
]
LINEAGE_TESTS = [
    "tests/test_goal_lineage_coordination_seal.py",
    "tests/test_aer_live_execution_lineage_subject_binding.py",
    "tests/test_aer_terminal_authority_lineage_seal.py",
    "tests/test_session_namespace_proof_closure.py",
]
RUNTIME_SESSION_TESTS = [
    "tests/test_session_identity_authority_seal.py",
    "tests/test_runtime_session_resume_identity_boundary.py",
    "tests/test_runtime_session_resume_v1.py",
    "tests/test_runtime_session_resume_seal_v1.py",
    "tests/test_runtime_execution_session_contract.py",
]
REPAIR_CHAIN_TESTS = [
    "tests/test_repair_chain_runtime.py",
    "tests/test_runtime_native_autonomous_repair_chain_v1.py",
    "tests/test_runtime_native_autonomous_repair_chain_v2_integration.py",
    "tests/test_runtime_native_autonomous_repair_chain_seal_v1.py",
    "tests/test_runtime_blockers.py",
]


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def run(label: str, args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        output = "\n".join(filter(None, (stdout, stderr))).strip()
        return {
            "suite": label,
            "status": "timeout",
            "returncode": 124,
            "command": subprocess.list2cmdline(args),
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "output_tail": output[-8000:] or "suite exceeded 90 second validation limit",
        }
    output = "\n".join(filter(None, (completed.stdout, completed.stderr))).strip()
    passed = sum(int(value) for value in re.findall(r"(\d+) passed", output))
    failed = sum(int(value) for value in re.findall(r"(\d+) failed", output))
    errors = sum(int(value) for value in re.findall(r"(\d+) error(?:s)?", output))
    return {
        "suite": label,
        "status": "pass" if completed.returncode == 0 else "fail",
        "returncode": completed.returncode,
        "command": subprocess.list2cmdline(args),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "output_tail": output[-8000:],
    }


def authority_consumers() -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"definitions": [], "calls": [], "overlays": []}
    for root_name in ("core", "tests"):
        for path in (ROOT / root_name).rglob("*.py"):
            try:
                source = path.read_text(encoding="utf-8-sig")
                tree = ast.parse(source, filename=str(path))
            except (OSError, SyntaxError, UnicodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_build_taskrunner_authority_context":
                    result["definitions"].append({"file": relative(path), "line": node.lineno, "symbol": node.name})
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_build_taskrunner_authority_context":
                    result["calls"].append({"file": relative(path), "line": node.lineno})
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute) and target.attr == "_build_taskrunner_authority_context":
                            result["overlays"].append({"file": relative(path), "line": node.lineno})
    for values in result.values():
        values.sort(key=lambda item: (item["file"], item["line"]))
    return result


def build_inventory() -> dict[str, Any]:
    stage14 = load_json(STAGE14)
    consumers = authority_consumers()
    nonmainline = stage14.get("non_mainline_issues", [])
    bridges = stage14.get("compatibility_bridges", [])
    taskrunner_source = (ROOT / "core/runtime/task_runner.py").read_text(encoding="utf-8-sig")
    contract_source = (ROOT / "core/runtime/taskrunner_authority_contract.py").read_text(encoding="utf-8-sig")
    return {
        "stage": "Stage17A — Wave1 Authority Context Migration",
        "canonical_owner": "core.runtime.taskrunner_authority_contract.build_taskrunner_authority_context",
        "entrypoint": "core.runtime.task_runner.TaskRunner._build_taskrunner_authority_context",
        "consumers": consumers,
        "active_authority_context_overlay_count": len(consumers["overlays"]),
        "compatibility_classification": {
            "retired_active_overlay": "_zero_boundary_build_taskrunner_authority_context assignment",
            "inactive_legacy_helpers_visible": "_zero_boundary_build_taskrunner_authority_context" in taskrunner_source,
            "scheduler_boundary_overlay_deferred": "apply_boundary_authority_overlay(Scheduler)" in (ROOT / "core/tasks/scheduler.py").read_text(encoding="utf-8-sig"),
            "scheduler_boundary_overlay_reason": "tracked compatibility bridge; it no longer owns TaskRunner authority propagation and remains visible for Wave8 retirement",
            "compatibility_bridge_count": len(bridges),
            "compatibility_bridge_ids": [item.get("tracking_id") for item in bridges],
        },
        "propagation_graph_before": [
            "Scheduler._build_scheduler_authority_context",
            "Scheduler._run_step_via_task_runner",
            "RuntimeDispatcher.run_scheduler_boundary",
            "TaskRunner._build_taskrunner_authority_context (module-level overlay replacement)",
            "delegate_taskrunner_execution_capability",
            "StepExecutor.execute_step",
        ],
        "propagation_graph_after": [
            "Scheduler._build_scheduler_authority_context",
            "Scheduler canonical root-lineage normalization",
            "Scheduler._run_step_via_task_runner",
            "RuntimeDispatcher.run_scheduler_boundary",
            "TaskRunner._build_taskrunner_authority_context (class entrypoint)",
            "taskrunner_authority_contract.build_taskrunner_authority_context",
            "delegate_taskrunner_execution_capability",
            "StepExecutor.execute_step",
        ],
        "domain_propagation": {
            "authority_context": "incoming scheduler context + immutable capability provenance",
            "runtime_session": ["session_id", "runtime_session_id", "operator_session_id", "persistent_operator_session_id"],
            "goal_lineage": "canonical goal_lineage plus runtime_identity and runtime_identity_graph",
            "continuation_chain": ["continuation_id", "parent_continuation_id", "continuation_chain", "continuation_lineage"],
            "repair_chain": ["repair_chain_id", "repair_context"],
        },
        "invariants": {
            "runtime_identity_preserved": all(token in contract_source for token in ("runtime_identity", "runtime_identity_graph")),
            "goal_lineage_preserved": "goal_lineage" in contract_source,
            "continuation_chain_preserved": "continuation_chain" in contract_source,
            "repair_chain_preserved": "repair_chain_id" in contract_source,
            "scheduler_delegation_boundary_preserved": "run_scheduler_boundary(" in (ROOT / "core/tasks/scheduler.py").read_text(encoding="utf-8-sig"),
            "taskrunner_does_not_grant_execution_authority": '"execution_authority_granted": False' in contract_source,
        },
        "non_mainline_issue_reporting": {
            "covered": len(nonmainline),
            "total": 6,
            "status": "preserved" if len(nonmainline) == 6 else "fail",
            "tracking_ids": [item.get("tracking_id") for item in nonmainline],
            "records": nonmainline,
        },
    }


def build_validation(inventory: dict[str, Any]) -> dict[str, Any]:
    suites = {
        "compileall": run("compileall", [sys.executable, "-m", "compileall", "-q", "core", "cli", "tests", "tools"]),
        "ownership": run("ownership", [sys.executable, "-m", "pytest", "-q", *OWNERSHIP_TESTS]),
        "authority": run("authority", [sys.executable, "-m", "pytest", "-q", *AUTHORITY_TESTS]),
        "lineage": run("lineage", [sys.executable, "-m", "pytest", "-q", *LINEAGE_TESTS]),
        "runtime_session": run("runtime_session", [sys.executable, "-m", "pytest", "-q", *RUNTIME_SESSION_TESTS]),
        "repair_chain": run("repair_chain", [sys.executable, "-m", "pytest", "-q", *REPAIR_CHAIN_TESTS]),
    }
    invariant_pass = all(inventory["invariants"].values())
    suites_pass = all(item["status"] == "pass" for item in suites.values())
    no_overlay = inventory["active_authority_context_overlay_count"] == 0
    nonmainline = inventory["non_mainline_issue_reporting"]["status"] == "preserved"
    wave1_complete = suites_pass and invariant_pass and no_overlay and nonmainline
    failures = [
        {"suite": name, "output_tail": item["output_tail"]}
        for name, item in suites.items()
        if item["status"] != "pass"
    ]
    blockers = [item["suite"] for item in failures]
    if not no_overlay:
        blockers.append("active_taskrunner_authority_context_overlay")
    if not invariant_pass:
        blockers.append("authority_propagation_invariant_failure")
    if not nonmainline:
        blockers.append("non_mainline_reporting_loss")
    return {
        "stage": inventory["stage"],
        "suite_results": suites,
        "failures": failures,
        "new_blockers": blockers,
        "wave1_status": "complete" if wave1_complete else "blocked",
        "wave2_ready": wave1_complete,
        "production_runtime_modified": True,
        "production_runtime_files": [
            "core/runtime/task_runner.py",
            "core/runtime/taskrunner_authority_contract.py",
            "core/tasks/scheduler.py",
        ],
        "tests_modified": True,
        "test_files": ["tests/test_taskrunner_authority_context_canonical_migration.py"],
    }


def write_report(inventory: dict[str, Any], validation: dict[str, Any]) -> None:
    lines = [
        "# Stage17A — Wave1 Authority Context Migration", "",
        "## Decision", "",
        f"- Wave1 status: **{validation['wave1_status']}**",
        f"- Wave2 ready: **{str(validation['wave2_ready']).lower()}**",
        f"- Active TaskRunner authority overlays: {inventory['active_authority_context_overlay_count']}",
        f"- New blockers: {', '.join(validation['new_blockers']) or 'none'}", "",
        "## Authority propagation before", "",
    ]
    lines.extend(f"{index}. `{item}`" for index, item in enumerate(inventory["propagation_graph_before"], 1))
    lines.extend(["", "## Authority propagation after", ""])
    lines.extend(f"{index}. `{item}`" for index, item in enumerate(inventory["propagation_graph_after"], 1))
    lines.extend(["", "## Domain preservation", ""])
    for name, value in inventory["domain_propagation"].items():
        lines.append(f"- `{name}`: {value}")
    lines.extend(["", "## Validation", ""])
    for name, result in validation["suite_results"].items():
        lines.append(f"- `{name}`: {result['status']} ({result['passed']} passed, {result['failed']} failed, {result['errors']} errors)")
    lines.extend([
        "", "## Compatibility and non-mainline reporting", "",
        f"- Compatibility bridges visible: {inventory['compatibility_classification']['compatibility_bridge_count']} / 15",
        f"- Non-mainline issues: {inventory['non_mainline_issue_reporting']['covered']} / 6 preserved",
        "- Scheduler boundary compatibility overlay remains visible for its assigned later retirement wave; it does not own TaskRunner authority propagation.", "",
    ])
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    inventory = build_inventory()
    INVENTORY.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    validation = build_validation(inventory)
    VALIDATION.write_text(json.dumps(validation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(inventory, validation)
    print(f"authority_consumers: {len(inventory['consumers']['calls'])}")
    print(f"active_authority_context_overlays: {inventory['active_authority_context_overlay_count']}")
    print(f"non_mainline_issue_reporting: {inventory['non_mainline_issue_reporting']['covered']} / 6 preserved")
    print(f"wave1_status: {validation['wave1_status']}")
    print(f"wave2_ready: {str(validation['wave2_ready']).lower()}")
    print(f"new_blockers: {len(validation['new_blockers'])}")
    return 0 if validation["wave2_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
