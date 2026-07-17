from __future__ import annotations

import ast
from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy, pytest.mark.integration]



ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = (
    ROOT / "core" / "runtime",
    ROOT / "core" / "tasks",
    ROOT / "core" / "adaptive",
)

ALLOWED_STATUS_WRITE_FILES = {
    "core/runtime/runtime_state_machine.py",
    "core/runtime/task_runtime.py",
    "core/goals/goal_repository.py",
    "core/goals/goal_state_validator.py",
}

ALLOWED_NON_RUNTIME_STATUS_SUFFIXES = (
    "_status",
    "review_status",
    "handoff_status",
    "authority_handoff_status",
    "canonical_status",
    "constraint_status",
    "goal_status",
    "runtime_mutation_plan_graph_status",
    "controlled_mutation_transaction_status",
    "governed_engineering_transaction_batch_status",
)

HIGH_RISK_RUNTIME_STATUS_WRITERS = {
    "core/adaptive/adaptive_runtime_resume.py",
    "core/runtime/long_engineering_runtime.py",
    "core/runtime/mutation_boundary.py",
    "core/runtime/persistent_engineering_session.py",
    "core/runtime/persistent_runtime_orchestrator.py",
    "core/runtime/recovery_replay_closure.py",
    "core/runtime/runtime_dispatcher.py",
    "core/runtime/runtime_recovery_continuation.py",
    "core/runtime/runtime_session_resume.py",
    "core/runtime/task_runner.py",
    "core/runtime/thin_runtime_bridge.py",
    "core/runtime/work_package_queue.py",
    "core/tasks/engineering_goal_scheduler.py",
    "core/tasks/scheduler.py",
    "core/tasks/scheduler_core/public_task_record_helpers.py",
    "core/tasks/scheduler_core/queue_sync_helpers.py",
    "core/tasks/scheduler_core/repair_injection_execution.py",
    "core/tasks/scheduler_core/repo_state_helpers.py",
    "core/tasks/scheduler_core/runtime_overlay_helpers.py",
    "core/tasks/scheduler_core/runtime_resume_gate.py",
    "core/tasks/scheduler_core/simple_runner_helpers.py",
    "core/tasks/task_repository.py",
}


def _repo_rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_status_key(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and node.value == "status":
        return True
    if isinstance(node, ast.Str) and node.s == "status":
        return True
    return False


def _target_name(node: ast.AST) -> str:
    if isinstance(node, ast.Subscript):
        value = node.value
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            return value.attr
    return ""


def _is_runtime_status_target(target: ast.Subscript) -> bool:
    name = _target_name(target)
    if not name:
        # Nested domain records (for example replanning_history[-1]["status"])
        # are not canonical Runtime lifecycle projections.
        return False
    if name.endswith(ALLOWED_NON_RUNTIME_STATUS_SUFFIXES):
        return False
    return name in {
        "state",
        "task",
        "runtime_state",
        "safe_runtime_state",
        "next_task",
        "effective_task",
        "runtime_payload",
        "task_payload",
        "journal",
        "payload",
        "record",
        "result",
        "execution",
        "after",
        "updated_task",
    }


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _status_writes(path: Path) -> list[tuple[int, str]]:
    source = _source(path)
    tree = ast.parse(source, filename=str(path))
    writes: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and _is_status_key(target.slice):
                    if _is_runtime_status_target(target):
                        writes.append(
                            (
                                node.lineno,
                                ast.get_source_segment(source, node) or "status write",
                            )
                        )

        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Subscript) and _is_status_key(target.slice):
                if _is_runtime_status_target(target):
                    writes.append(
                        (
                            node.lineno,
                            ast.get_source_segment(source, node) or "status write",
                        )
                    )

    return writes


def test_runtime_status_write_authority_is_enforced() -> None:
    unauthorized: dict[str, list[tuple[int, str]]] = {}

    for scan_dir in SCAN_DIRS:
        for path in scan_dir.rglob("*.py"):
            rel = _repo_rel(path)
            if rel in ALLOWED_STATUS_WRITE_FILES:
                continue
            writes = _status_writes(path)
            if writes:
                unauthorized[rel] = writes

    assert not unauthorized, {
        "unauthorized_runtime_status_writers": unauthorized,
        "allowed_status_write_files": sorted(ALLOWED_STATUS_WRITE_FILES),
        "required_boundary": "call TaskRuntime/project_runtime_status or state-machine APIs",
    }


def test_previous_high_risk_status_writers_are_projection_clients() -> None:
    findings: dict[str, list[tuple[int, str]]] = {}

    for rel in HIGH_RISK_RUNTIME_STATUS_WRITERS:
        path = ROOT / rel
        if not path.exists():
            continue
        writes = _status_writes(path)
        if writes:
            findings[rel] = writes

    assert not findings, {
        "high_risk_direct_status_writers_remaining": findings,
        "required_boundary": "call TaskRuntime/project_runtime_status or state-machine APIs",
    }


def test_runtime_status_canonical_owner_files_are_allowed() -> None:
    for rel in ALLOWED_STATUS_WRITE_FILES:
        assert (ROOT / rel).exists(), rel


def test_task_runtime_exposes_projection_boundary() -> None:
    source = _source(ROOT / "core/runtime/task_runtime.py")
    assert "def project_runtime_status(" in source
    assert "payload[\"status\"] = status" in source
