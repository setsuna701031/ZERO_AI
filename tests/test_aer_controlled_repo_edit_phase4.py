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
                "goal": "Apply Phase 4 controlled repo edit",
                "mode": "execute",
                "approval": True,
                "edits": edits,
            }
        )
    )


def _seed_allowed_files(repo_root: Path) -> tuple[Path, Path]:
    readme = repo_root / "README.md"
    package_file = repo_root / "core/tasks/work_package_phase4_target.py"
    package_file.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text("# Phase 4\n", encoding="utf-8")
    package_file.write_text("VALUE = 'original'\n", encoding="utf-8")
    return readme, package_file


def _successful_multi_edit(repo_root: Path, package_id: str = "phase4_change_set") -> dict[str, object]:
    _seed_allowed_files(repo_root)
    return _run_multi_edit(
        repo_root,
        package_id=package_id,
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nPhase 4 README marker.\n",
                "verify_contains": "Phase 4 README marker.",
            },
            {
                "operation": "write_file",
                "target_path": "core/tasks/work_package_phase4_target.py",
                "content": "VALUE = 'phase4'\n",
                "verify_contains": "VALUE = 'phase4'",
            },
        ],
    )


def _read_json(repo_root: Path, relative_path: str) -> dict[str, object]:
    return json.loads((repo_root / relative_path).read_text(encoding="utf-8"))


def test_change_set_generated_for_multi_file_repo_edit(tmp_path: Path) -> None:
    response = _successful_multi_edit(tmp_path, "phase4_generated")

    result = response["work_package_result"]
    change_set = result["change_set"]
    assert result["ok"] is True
    assert change_set["schema"] == "zero.work_package.change_set.v1"
    assert change_set["change_set_id"] == "change_set:phase4_generated"
    assert change_set["goal"] == "Apply Phase 4 controlled repo edit"
    assert change_set["complete"] is True
    assert change_set["successful"] is True
    assert change_set["edit_plan"]["schema"] == "zero.work_package.structured_edit_plan.v1"
    assert change_set["impact_analysis"]["schema"] == "zero.work_package.impact_analysis.v1"
    assert change_set["execution_result"]["ok"] is True
    assert change_set["result_summary"]["status"] == "success"


def test_change_set_contains_all_target_files(tmp_path: Path) -> None:
    response = _successful_multi_edit(tmp_path, "phase4_all_files")

    change_set = response["work_package_result"]["change_set"]
    expected_files = ["README.md", "core/tasks/work_package_phase4_target.py"]
    assert change_set["files"] == expected_files
    assert [operation["target_path"] for operation in change_set["operations"]] == expected_files
    assert change_set["result_summary"]["target_file_count"] == 2


def test_verification_set_is_recorded(tmp_path: Path) -> None:
    response = _successful_multi_edit(tmp_path, "phase4_verification_set")

    result = response["work_package_result"]
    verification_set = result["change_set"]["verification_set"]
    assert result["verification_set"] == verification_set
    assert verification_set["schema"] == "zero.work_package.verification_set.v1"
    assert verification_set["ok"] is True
    assert [item["target_path"] for item in verification_set["targets"]] == [
        "README.md",
        "core/tasks/work_package_phase4_target.py",
    ]


def test_rollback_status_is_recorded(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)
    response = _run_multi_edit(
        tmp_path,
        package_id="phase4_rollback_status",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nTemporary Phase 4 edit.\n",
                "verify_contains": "Temporary Phase 4 edit.",
            },
            {
                "operation": "write_file",
                "target_path": "core/tasks/work_package_phase4_target.py",
                "content": "VALUE = 'temporary'\n",
                "verify_contains": "marker that is intentionally absent",
            },
        ],
    )

    change_set = response["work_package_result"]["change_set"]
    assert response["ok"] is False
    assert change_set["successful"] is False
    assert change_set["rollback_status"]["rollback_performed"] is True
    assert change_set["rollback_status"]["ok"] is True
    assert change_set["result_summary"]["rollback_performed"] is True


def test_blocked_target_does_not_produce_successful_change_set(tmp_path: Path) -> None:
    readme, _package_file = _seed_allowed_files(tmp_path)
    before_readme = readme.read_text(encoding="utf-8")

    response = _run_multi_edit(
        tmp_path,
        package_id="phase4_blocked_change_set",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nShould not land.\n",
                "verify_contains": "Should not land.",
            },
            {
                "operation": "write_file",
                "target_path": "core/runtime/phase4_blocked.py",
                "content": "bad\n",
                "verify_contains": "bad",
            },
        ],
    )

    result = response["work_package_result"]
    change_set = result["change_set"]
    assert response["ok"] is False
    assert result["blocked"] is True
    assert change_set["complete"] is True
    assert change_set["successful"] is False
    assert change_set["execution_result"]["status"] == "blocked"
    assert "core/runtime/phase4_blocked.py" in change_set["files"]
    assert readme.read_text(encoding="utf-8") == before_readme
    assert not (tmp_path / "core/runtime/phase4_blocked.py").exists()


def test_result_artifacts_include_complete_change_set(tmp_path: Path) -> None:
    response = _successful_multi_edit(tmp_path, "phase4_artifact_bundle")
    result = response["work_package_result"]
    final = _read_json(tmp_path, result["result_path"])
    evidence = _read_json(tmp_path, result["evidence_path"])
    audit = _read_json(tmp_path, result["audit_path"])

    for package in (result, final, evidence, audit):
        change_set = package["change_set"]
        assert change_set["complete"] is True
        assert change_set["edit_plan"]
        assert change_set["impact_analysis"]
        assert change_set["files"] == ["README.md", "core/tasks/work_package_phase4_target.py"]
        assert change_set["operations"]
        assert change_set["verification_set"]["ok"] is True
        assert change_set["rollback_status"]["rollback_performed"] is False
        assert change_set["execution_result"]["ok"] is True
        assert change_set["result_summary"]["ok"] is True
