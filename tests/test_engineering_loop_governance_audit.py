from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime
from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import (
    GoalCompletionAuthority,
    is_accepted_goal_completion_result,
)
from core.goals.goal_lineage_contract import (
    attach_goal_lineage,
    create_root_goal_lineage,
    extract_goal_lineage,
)
from core.runtime.runtime_session_resume import build_runtime_resume_plan
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.work_package_queue import RuntimePackageQueue
from core.runtime.planner_runtime_dispatch import planner_result_to_persistent_runtime_task
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import EngineeringGoalRunner
from core.tasks.engineering_runtime_orchestrator import EngineeringRuntimeOrchestrator
from core.tasks.work_package_runtime_intake import build_package_record


LOOP_PATH = Path("core/tasks/engineering_goal_loop.py")
RUNNER_PATH = Path("core/tasks/engineering_goal_runner.py")
REPOSITORY_PATH = Path("core/tasks/engineering_goal_repository.py")
ENGINEERING_BOUNDARY_PATHS = (LOOP_PATH, RUNNER_PATH)


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


def _calls(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(_source(path), filename=str(path))):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name):
            names.append(function.id)
        elif isinstance(function, ast.Attribute):
            names.append(function.attr)
    return names


def _lineage(goal_id: str = "goal-a") -> dict[str, str]:
    return create_root_goal_lineage(
        goal_id=goal_id,
        session_id="engineering-session-a",
        runtime_session_id="runtime-session-a",
    )


def test_engineering_goal_lineage_closure(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    lineage = _lineage()
    saved = repository.save_goal(attach_goal_lineage({"goal_id": "goal-a", "summary": "Audit"}, lineage))
    loaded = repository.load_goal("goal-a")

    assert extract_goal_lineage(saved, require_complete=True) == lineage
    assert extract_goal_lineage(loaded, require_complete=True) == lineage
    with pytest.raises(ValueError, match="invalid_runtime_identity.*session_id"):
        repository.save_goal(
            attach_goal_lineage(
                {"goal_id": "goal-invalid", "summary": "Invalid"},
                {**_lineage("goal-invalid"), "session_id": "system"},
            )
        )


def test_engineering_session_closure(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"goal_id": "goal-a", "summary": "Audit"})
    captured: dict[str, str] = {}

    class Runner:
        def run_goal(self, goal_id: str, *, goal_lineage=None):
            captured.update(goal_lineage or {})
            return {"ok": False, "goal_id": goal_id, "adaptive_decision": {"decision": "blocked"}}

    EngineeringGoalLoop(repo_root=tmp_path, repository=repository, runner=Runner()).run_one_cycle(
        "goal-a",
        goal_lineage=goal["goal_lineage"],
    )
    assert captured["session_id"] == goal["session_id"]
    assert captured["runtime_session_id"] == goal["runtime_session_id"]
    assert captured["session_id"] != captured["runtime_session_id"]


def test_goal_transition_governance_closure(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    created = repository.save_goal({"goal_id": "goal-a", "summary": "Audit"})
    updated = repository.update_goal("goal-a", {"status": "blocked", "reason": "audit pause"})
    assert extract_goal_lineage(updated, require_complete=True) == extract_goal_lineage(
        created, require_complete=True
    )

    with pytest.raises(ValueError, match="engineering_goal_lineage_conflict:session_id"):
        repository.update_goal(
            "goal-a",
            {"metadata": {"goal_lineage": {**created["goal_lineage"], "session_id": "other-session"}}},
        )


def test_goal_completion_evidence_closure(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"goal_id": "goal-a", "summary": "Audit", "status": "active"})
    rejected = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[{"evidence_id": "unsealed"}],
        all_subgoals_completed=True,
        goal_lineage=goal["goal_lineage"],
    )
    assert not is_accepted_goal_completion_result(rejected, goal_id="goal-a")

    evidence = EvidenceValidator().validate(
        EvidenceRecord(
            "evidence-a",
            "goal-a",
            None,
            "audit",
            "verified",
            "now",
            metadata={**goal["goal_lineage"], "goal_lineage": goal["goal_lineage"]},
        )
    )
    accepted = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[evidence],
        all_subgoals_completed=True,
        goal_lineage=goal["goal_lineage"],
    )
    other_lineage = create_root_goal_lineage(
        goal_id="goal-a",
        session_id="other-session",
        runtime_session_id="other-runtime-session",
    )
    other_evidence = EvidenceValidator().validate(
        EvidenceRecord(
            "evidence-other",
            "goal-a",
            None,
            "audit",
            "verified",
            "now",
            metadata={**other_lineage, "goal_lineage": other_lineage},
        )
    )
    wrong_session_attestation = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[other_evidence],
        all_subgoals_completed=True,
        goal_lineage=other_lineage,
    )
    with pytest.raises(ValueError, match="canonical_completion_attestation_required"):
        repository.update_goal(
            "goal-a",
            {"status": "completed", "evidence_refs": [other_evidence.to_dict()]},
            completion_attestation=wrong_session_attestation,
        )
    completed = repository.update_goal(
        "goal-a",
        {"status": "completed", "evidence_refs": [evidence.to_dict()]},
        completion_attestation=accepted,
    )
    assert completed["status"] == "completed"
    assert extract_goal_lineage(completed, require_complete=True) == goal["goal_lineage"]


def test_engineering_runner_governance_closure(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"goal_id": "goal-a", "summary": "Audit"})
    runner = EngineeringGoalRunner(repo_root=tmp_path, repository=repository)
    request = runner.build_runtime_request([goal], selected_goal_id="goal-a")
    request_lineage = extract_goal_lineage(request["goals"][0], require_complete=True)
    assert request_lineage == goal["goal_lineage"]
    assert "goal_lineage" in inspect.signature(runner.run_goal).parameters


def test_engineering_loop_governance_closure() -> None:
    source = _source(LOOP_PATH)
    assert "goal_lineage=lineage" in source
    assert "inspect.signature" not in source
    assert "else run_goal(" not in source


def test_continuation_governance_closure() -> None:
    lineage = _lineage()
    continued = ContinuationRuntime.start("goal-a", goal_lineage=lineage).record_work_item(
        {"goal_id": "goal-a__continuation_1", "branch_id": "continuation-1"}
    )
    assert continued.root_goal_id == lineage["root_goal_id"]
    assert continued.source_goal_id == lineage["source_goal_id"]
    assert continued.goal_lineage_id == lineage["goal_lineage_id"]
    assert continued.session_id == lineage["session_id"]
    assert continued.runtime_session_id == lineage["runtime_session_id"]


def test_replan_governance_closure() -> None:
    lineage = _lineage()
    replanned = ReplanRuntime.start(goal_lineage=lineage).record_replan(
        {"replan_request_id": "replan-1"}
    )
    assert replanned.root_goal_id == lineage["root_goal_id"]
    assert replanned.source_goal_id == lineage["source_goal_id"]
    assert replanned.goal_lineage_id == lineage["goal_lineage_id"]
    assert replanned.session_id == lineage["session_id"]
    assert replanned.runtime_session_id == lineage["runtime_session_id"]


def test_resume_governance_closure(tmp_path) -> None:
    lineage = _lineage()
    task = attach_goal_lineage({"task_id": "task-a", "status": "running"}, lineage)
    plan = build_runtime_resume_plan(
        [task],
        workspace_root=tmp_path,
        storage_path=tmp_path / "resume.json",
        session_id=lineage["session_id"],
    )
    resumed = plan["lineage_by_task_id"]["task-a"]
    for field in ("root_goal_id", "source_goal_id", "goal_lineage_id", "session_id", "runtime_session_id"):
        assert resumed[field] == lineage[field]


def test_no_direct_runtime_authority_mint() -> None:
    prohibited = ("runtime_authority", "runtime_execution_authority", "runtime_grant_issuer")
    findings = [f"{path}:{module}" for path in ENGINEERING_BOUNDARY_PATHS for module in _imports(path) if any(item in module for item in prohibited)]
    assert not findings, "direct runtime authority imports:\n" + "\n".join(findings)


def test_no_direct_runtime_capability_mint() -> None:
    findings = [f"{path}:{module}" for path in ENGINEERING_BOUNDARY_PATHS for module in _imports(path) if "runtime_capability" in module]
    assert not findings, "direct runtime capability imports:\n" + "\n".join(findings)


def test_no_direct_mutation_path() -> None:
    prohibited = {"apply_mutation", "execute_mutation", "mutate_runtime", "record_apply"}
    findings = [f"{path}:{call}" for path in ENGINEERING_BOUNDARY_PATHS for call in _calls(path) if call in prohibited]
    assert not findings, "direct mutation calls:\n" + "\n".join(findings)


def test_no_direct_persistence_path() -> None:
    prohibited = {"save_goal", "update_goal", "write_text", "write_bytes", "_append", "_write_records"}
    findings = [f"{path}:{call}" for path in ENGINEERING_BOUNDARY_PATHS for call in _calls(path) if call in prohibited]
    assert not findings, "direct persistence calls:\n" + "\n".join(findings)
    assert "adaptive_persistence_gateway.persist_cycle" not in _source(LOOP_PATH)


def test_no_quiet_success_on_governance_conflict(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"goal_id": "goal-a", "summary": "Audit"})
    runner = EngineeringGoalRunner(repo_root=tmp_path, repository=repository)
    request = runner.build_runtime_request([goal], selected_goal_id="goal-a")
    conflicting = attach_goal_lineage({"ok": True}, create_root_goal_lineage(goal_id="goal-b"))
    with pytest.raises(ValueError, match="engineering_runner_runtime_governance_identity_conflict"):
        runner._runner_result(
            ok=True,
            action="run_goal",
            goal_id="goal-a",
            runtime_request=request,
            runtime_result=conflicting,
            runtime_stdout="",
            runtime_root_cause={},
            adaptive_decision={"decision": "complete"},
            issue_summary={},
        )

    (tmp_path / "runtime" / "goals" / "goals.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_engineering_goal_repository"):
        repository.list_goals()


def test_no_legacy_engineering_bypass() -> None:
    imports = _imports(LOOP_PATH) + _imports(RUNNER_PATH)
    assert not [module for module in imports if "_archive_candidate" in module]
    loop_source = _source(LOOP_PATH)
    assert "inspect.signature" not in loop_source
    assert "run_goal(_clean_text(goal_id))" not in loop_source
    assert "goal_lineage=lineage" in loop_source


def test_work_package_side_route_mints_one_canonical_root_at_intake() -> None:
    package = build_package_record(
        {
            "package_id": "side-route",
            "title": "Side route",
            "goal": "Audit side route",
            "description": "Audit",
            "target_files": ["core/runtime/runtime_dispatcher.py"],
            "requirements": ["sealed runtime"],
            "hard_boundary": ["no bypass"],
        }
    ).to_dict()
    lineage = extract_goal_lineage(package, require_complete=True, reject_conflicts=True)
    assert lineage["goal_id"] == "side-route"
    assert lineage["session_id"] != lineage["runtime_session_id"]


def test_runtime_dispatcher_scheduler_boundary_rejects_missing_lineage(tmp_path) -> None:
    class Runner:
        def run_task(self, **_kwargs):
            raise AssertionError("missing lineage must be rejected before TaskRunner")

    dispatcher = RuntimeDispatcher(
        queue=RuntimePackageQueue(repo_root=tmp_path),
        task_runner=Runner(),
        workspace_root=tmp_path,
    )
    result = dispatcher.run_scheduler_boundary(
        {"task_id": "unsealed", "package_id": "unsealed", "steps": [{"type": "inspect"}]}
    )
    assert result["ok"] is False
    assert result["executed"] is False
    assert "canonical_lineage_required" in result["error"]


def test_planner_runtime_side_route_carries_canonical_lineage() -> None:
    task = planner_result_to_persistent_runtime_task(
        user_input="persistent runtime",
        planner_result={"persistent_runtime": True, "steps": [{"type": "inspect"}]},
    )
    assert extract_goal_lineage(task, require_complete=True, reject_conflicts=True)


def test_engineering_runtime_rejects_unsealed_goal_before_scheduler(tmp_path) -> None:
    class Scheduler:
        def schedule_next_goal(self, _goals):
            raise AssertionError("unsealed goal must be rejected before scheduler")

    orchestrator = EngineeringRuntimeOrchestrator(repo_root=tmp_path, scheduler=Scheduler())
    with pytest.raises(ValueError, match="goal_lineage_missing_fields"):
        orchestrator.run([{"goal_id": "unsealed", "status": "pending"}])


def test_specialized_work_package_route_uses_sealed_runtime_dispatcher() -> None:
    source = _source(Path("core/tasks/engineering_goal_work_package_mainline.py"))
    assert "WorkPackageScheduler(" not in source
    assert "RuntimeWorkPackageOperator(" in source
    assert "RuntimeDispatcher(" in source


def test_adaptive_persistence_has_no_unvalidated_evidence_fallback() -> None:
    source = _source(Path("core/tasks/adaptive_persistence_gateway.py"))
    assert "return copy.deepcopy(dict(decision_evidence))" not in source
    assert "adaptive_persistence_requires_evidence_authority" in source
