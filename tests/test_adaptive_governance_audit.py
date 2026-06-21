from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime
from core.goals.goal_lineage_contract import create_root_goal_lineage


AUDIT_TARGETS = (
    Path("core/adaptive/continuation_runtime.py"),
    Path("core/adaptive/continuation_coordinator.py"),
    Path("core/adaptive/replan_runtime.py"),
    Path("core/adaptive/replan_coordinator.py"),
    Path("core/tasks/engineering_goal_loop.py"),
    Path("core/tasks/engineering_goal_runner.py"),
)

ADAPTIVE_TARGETS = AUDIT_TARGETS[:4]
LEGACY_OR_PARALLEL_MARKERS = (
    "legacy_continuation",
    "legacy_replan",
    "parallel_adaptive",
    "alternate_adaptive",
)
DIRECT_GOVERNANCE_MODULES = (
    "core.runtime.runtime_authority",
    "core.runtime.runtime_capability",
    "core.runtime.runtime_identity",
    "core.runtime.runtime_ownership",
    "core.runtime.runtime_mutation",
    "core.runtime.governed_mutation",
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _imports(path: Path) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(ast.parse(_source(path), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _lineage() -> dict[str, str]:
    return create_root_goal_lineage(
        goal_id="goal-a",
        session_id="session-a",
        runtime_session_id="runtime-session-a",
    )


def test_audit_scope_exists_and_parses() -> None:
    missing = [str(path) for path in AUDIT_TARGETS if not path.is_file()]
    assert not missing, f"adaptive governance audit targets missing: {missing}"
    for path in AUDIT_TARGETS:
        ast.parse(_source(path), filename=str(path))


def test_no_adaptive_authority_ownership_or_mutation_bypass_imports() -> None:
    findings: list[str] = []
    for path in ADAPTIVE_TARGETS:
        for module in _imports(path):
            if module.startswith(DIRECT_GOVERNANCE_MODULES):
                findings.append(f"{path}: direct governance import {module}")
    assert not findings, "non-mainline adaptive governance paths:\n" + "\n".join(findings)


def test_no_parallel_planner_or_legacy_continuation_replan_path() -> None:
    findings: list[str] = []
    for path in AUDIT_TARGETS:
        lowered = _source(path).lower()
        for marker in LEGACY_OR_PARALLEL_MARKERS:
            if marker in lowered:
                findings.append(f"{path}: {marker}")

    loop_imports = _imports(Path("core/tasks/engineering_goal_loop.py"))
    runner_imports = _imports(Path("core/tasks/engineering_goal_runner.py"))
    planner_imports = [module for module in loop_imports + runner_imports if "adaptive_planner" in module]
    assert planner_imports == ["core.tasks.engineering_adaptive_planner"], (
        "parallel adaptive planner imports: " + repr(planner_imports)
    )
    assert not findings, "legacy or parallel adaptive paths:\n" + "\n".join(findings)


def test_adaptive_identity_is_derived_from_canonical_lineage_contract() -> None:
    findings: list[str] = []
    for path in ADAPTIVE_TARGETS:
        source = _source(path)
        if "core.goals.goal_lineage_contract" not in _imports(path):
            findings.append(f"{path}: canonical lineage contract not imported")
        for synthesized_default in ("goal-session-", "goal-runtime-", "runtime-session-"):
            if synthesized_default in source:
                findings.append(f"{path}: locally synthesized identity {synthesized_default}")
    assert not findings, "adaptive identity bypass findings:\n" + "\n".join(findings)


def test_runtime_bookkeeping_mutation_requires_internal_authority() -> None:
    continuation = ContinuationRuntime.start("goal-a", goal_lineage=_lineage())
    replan = ReplanRuntime.start(goal_lineage=_lineage())
    with pytest.raises(PermissionError, match="continuation_mutation_authority_required"):
        continuation.replace(continuation_count=1)
    with pytest.raises(PermissionError, match="replan_mutation_authority_required"):
        replan.replace(replan_count=1)


def test_continuation_preserves_governance_root_and_session() -> None:
    lineage = _lineage()
    runtime = ContinuationRuntime.start("goal-a", max_continuations=1, goal_lineage=lineage)
    continued = runtime.record_work_item(
        {"goal_id": "goal-a__continuation_1", "branch_id": "continuation-1"}
    )

    assert continued.root_goal_id == lineage["root_goal_id"]
    assert continued.source_goal_id == lineage["source_goal_id"]
    assert continued.session_id == lineage["session_id"]
    assert continued.runtime_session_id == lineage["runtime_session_id"]
    assert continued.goal_lineage_id == lineage["goal_lineage_id"]
    assert continued.branch_type == "continuation"
    assert continued.branch_id == "continuation-1"


def test_replan_preserves_governance_root_goal_and_session() -> None:
    lineage = _lineage()
    runtime = ReplanRuntime.start(max_replans=1, goal_lineage=lineage)
    replanned = runtime.record_replan({"replan_request_id": "replan-1"})

    assert replanned.root_goal_id == lineage["root_goal_id"]
    assert replanned.source_goal_id == lineage["source_goal_id"]
    assert replanned.goal_id == lineage["goal_id"]
    assert replanned.session_id == lineage["session_id"]
    assert replanned.runtime_session_id == lineage["runtime_session_id"]
    assert replanned.goal_lineage_id == lineage["goal_lineage_id"]
    assert replanned.branch_type == "replan"
    assert replanned.branch_id == "replan-1"
