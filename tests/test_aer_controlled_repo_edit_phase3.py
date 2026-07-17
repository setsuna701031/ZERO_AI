from __future__ import annotations

import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.planning.planner import Planner


def _run_multi_edit(repo_root: Path, *, package_id: str, edits: list[dict[str, object]]) -> dict[str, object]:
    return AgentLoop(planner=Planner(), repo_root=str(repo_root)).run(
        json.dumps(
            {
                "task_type": "aer_task",
                "repo_root": str(repo_root),
                "task_id": package_id,
                "goal": "Apply Phase 3 controlled repo edit",
                "mode": "execute",
                "approval": True,
                "edits": edits,
            }
        )
    )


def _seed_allowed_files(repo_root: Path) -> tuple[Path, Path]:
    readme = repo_root / "README.md"
    package_file = repo_root / "core/tasks/work_package_phase3_target.py"
    package_file.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text("# Phase 3\n", encoding="utf-8")
    package_file.write_text("VALUE = 'original'\n", encoding="utf-8")
    return readme, package_file


def _read_json(repo_root: Path, relative_path: str) -> dict[str, object]:
    return json.loads((repo_root / relative_path).read_text(encoding="utf-8"))


def test_edit_plan_generated_before_controlled_repo_edit(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)

    response = _run_multi_edit(
        tmp_path,
        package_id="phase3_plan_generated",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nPhase 3 plan marker.\n",
                "verify_contains": "Phase 3 plan marker.",
            }
        ],
    )

    result = response["work_package_result"]
    edit_plan = result["edit_plan"]
    assert result["ok"] is True
    assert edit_plan["schema"] == "zero.work_package.structured_edit_plan.v1"
    assert edit_plan["valid"] is True
    assert edit_plan["task_goal"] == "Apply Phase 3 controlled repo edit"
    assert edit_plan["target_files"] == ["README.md"]
    assert edit_plan["files_to_modify"][0]["reason"]
    assert edit_plan["files_to_modify"][0]["expected_effect"]
    assert edit_plan["files_to_modify"][0]["verification_method"]


def test_impact_analysis_generated_for_controlled_repo_edit(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)

    response = _run_multi_edit(
        tmp_path,
        package_id="phase3_impact_generated",
        edits=[
            {
                "operation": "write_file",
                "target_path": "core/tasks/work_package_phase3_target.py",
                "content": "VALUE = 'impact'\n",
                "verify_contains": "VALUE = 'impact'",
            }
        ],
    )

    impact = response["work_package_result"]["impact_analysis"]
    assert impact["schema"] == "zero.work_package.impact_analysis.v1"
    assert impact["valid"] is True
    assert impact["affected_modules"] == ["core/tasks"]
    assert "tests/test_aer_controlled_repo_edit_phase3.py" in impact["affected_tests"]
    assert "controlled_repo_edit_result_package" in impact["affected_contracts"]
    assert impact["risk_level"] == "medium"


def test_blocked_task_still_blocked_with_plan_and_impact(tmp_path: Path) -> None:
    readme, _package_file = _seed_allowed_files(tmp_path)
    before_readme = readme.read_text(encoding="utf-8")

    response = _run_multi_edit(
        tmp_path,
        package_id="phase3_blocked_still_blocked",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nShould not execute.\n",
                "verify_contains": "Should not execute.",
            },
            {
                "operation": "write_file",
                "target_path": "core/runtime/phase3_blocked.py",
                "content": "bad\n",
                "verify_contains": "bad",
            },
        ],
    )

    result = response["work_package_result"]
    assert response["ok"] is False
    assert result["blocked"] is True
    assert "blocked_target_prefix:core/runtime" in result["reason"]
    assert result["edit_plan"]["valid"] is True
    assert result["impact_analysis"]["valid"] is True
    assert result["execution_result"]["status"] == "blocked"
    assert result["rollback_status"]["rollback_performed"] is False
    assert readme.read_text(encoding="utf-8") == before_readme
    assert not (tmp_path / "core/runtime/phase3_blocked.py").exists()


def test_rollback_still_works_with_phase3_package(tmp_path: Path) -> None:
    readme, package_file = _seed_allowed_files(tmp_path)
    before_readme = readme.read_text(encoding="utf-8")
    before_package = package_file.read_text(encoding="utf-8")

    response = _run_multi_edit(
        tmp_path,
        package_id="phase3_rollback_still_works",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nTemporary Phase 3 edit.\n",
                "verify_contains": "Temporary Phase 3 edit.",
            },
            {
                "operation": "write_file",
                "target_path": "core/tasks/work_package_phase3_target.py",
                "content": "VALUE = 'temporary'\n",
                "verify_contains": "marker that is intentionally absent",
            },
        ],
    )

    result = response["work_package_result"]
    assert response["ok"] is False
    assert result["reason"] == "verification_failed"
    assert result["rollback_status"]["rollback_performed"] is True
    assert result["rollback_status"]["ok"] is True
    assert result["changed_files"] == []
    assert readme.read_text(encoding="utf-8") == before_readme
    assert package_file.read_text(encoding="utf-8") == before_package


def test_result_package_contains_plan_impact_execution_verification_and_rollback(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)

    response = _run_multi_edit(
        tmp_path,
        package_id="phase3_result_package",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nPhase 3 result package marker.\n",
                "verify_contains": "Phase 3 result package marker.",
            }
        ],
    )

    result = response["work_package_result"]
    final = _read_json(tmp_path, result["result_path"])
    evidence = _read_json(tmp_path, result["evidence_path"])

    for package in (result, final):
        assert package["plan"]["schema"] == "zero.work_package.structured_edit_plan.v1"
        assert package["impact_analysis"]["schema"] == "zero.work_package.impact_analysis.v1"
        assert package["execution_result"]["schema"] == "zero.work_package.execution_result.v1"
        assert package["verification_result"]["ok"] is True
        assert package["rollback_status"]["rollback_performed"] is False

    assert result["execution"]["existing_multi_file_transaction_path"]
    assert result["execution"]["existing_rollback_path"]
    assert result["execution"]["existing_verification_path"]
    assert evidence["edit_plan"]["valid"] is True
    assert evidence["impact_analysis"]["valid"] is True
