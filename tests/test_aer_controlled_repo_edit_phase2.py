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
                "goal": "Apply multi-file controlled repo edit",
                "mode": "execute",
                "approval": True,
                "edits": edits,
            }
        )
    )


def _seed_allowed_files(repo_root: Path) -> tuple[Path, Path]:
    readme = repo_root / "README.md"
    package_file = repo_root / "core/tasks/work_package_phase2_target.py"
    package_file.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text("# Phase 2\n", encoding="utf-8")
    package_file.write_text("VALUE = 'original'\n", encoding="utf-8")
    return readme, package_file


def _read_json(repo_root: Path, relative_path: str) -> dict[str, object]:
    return json.loads((repo_root / relative_path).read_text(encoding="utf-8"))


def test_multi_file_controlled_repo_edit_success(tmp_path: Path) -> None:
    readme, package_file = _seed_allowed_files(tmp_path)

    response = _run_multi_edit(
        tmp_path,
        package_id="phase2_multi_success",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nPhase 2 README marker.\n",
                "verify_contains": "Phase 2 README marker.",
            },
            {
                "operation": "write_file",
                "target_path": "core/tasks/work_package_phase2_target.py",
                "content": "VALUE = 'phase2'\n",
                "verify_contains": "VALUE = 'phase2'",
            },
        ],
    )

    result = response["work_package_result"]
    assert response["ok"] is True
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["package_id"] == "phase2_multi_success"
    assert result["task_id"] == "phase2_multi_success"
    assert result["target_files"] == ["README.md", "core/tasks/work_package_phase2_target.py"]
    assert result["changed_files"] == ["README.md", "core/tasks/work_package_phase2_target.py"]
    assert result["rollback_performed"] is False
    assert result["verification_result"]["ok"] is True
    assert "Phase 2 README marker." in readme.read_text(encoding="utf-8")
    assert package_file.read_text(encoding="utf-8") == "VALUE = 'phase2'\n"


def test_partial_failure_rolls_back_all_files(tmp_path: Path) -> None:
    readme, package_file = _seed_allowed_files(tmp_path)
    before_readme = readme.read_text(encoding="utf-8")
    before_package = package_file.read_text(encoding="utf-8")

    response = _run_multi_edit(
        tmp_path,
        package_id="phase2_partial_failure",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nThis must roll back.\n",
                "verify_contains": "This must roll back.",
            },
            {
                "operation": "append_file",
                "target_path": "core/tasks/work_package_phase2_missing.py",
                "content": "missing append target\n",
                "verify_contains": "missing append target",
            },
        ],
    )

    result = response["work_package_result"]
    assert response["ok"] is False
    assert result["ok"] is False
    assert result["rollback_performed"] is True
    assert result["changed_files"] == []
    assert readme.read_text(encoding="utf-8") == before_readme
    assert package_file.read_text(encoding="utf-8") == before_package
    assert not (tmp_path / "core/tasks/work_package_phase2_missing.py").exists()


def test_verification_failure_rolls_back_all_files(tmp_path: Path) -> None:
    readme, package_file = _seed_allowed_files(tmp_path)
    before_readme = readme.read_text(encoding="utf-8")
    before_package = package_file.read_text(encoding="utf-8")

    response = _run_multi_edit(
        tmp_path,
        package_id="phase2_verification_failure",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nTemporary README edit.\n",
                "verify_contains": "Temporary README edit.",
            },
            {
                "operation": "write_file",
                "target_path": "core/tasks/work_package_phase2_target.py",
                "content": "VALUE = 'temporary'\n",
                "verify_contains": "marker that is intentionally absent",
            },
        ],
    )

    result = response["work_package_result"]
    assert response["ok"] is False
    assert result["reason"] == "verification_failed"
    assert result["rollback_performed"] is True
    assert result["verification_result"]["ok"] is False
    assert result["changed_files"] == []
    assert readme.read_text(encoding="utf-8") == before_readme
    assert package_file.read_text(encoding="utf-8") == before_package


def test_protected_file_remains_blocked_before_any_edit(tmp_path: Path) -> None:
    readme, _package_file = _seed_allowed_files(tmp_path)
    before_readme = readme.read_text(encoding="utf-8")

    response = _run_multi_edit(
        tmp_path,
        package_id="phase2_protected_blocked",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nShould not land.\n",
                "verify_contains": "Should not land.",
            },
            {
                "operation": "write_file",
                "target_path": "core/runtime/phase2_blocked.py",
                "content": "bad\n",
                "verify_contains": "bad",
            },
        ],
    )

    result = response["work_package_result"]
    assert response["ok"] is False
    assert result["blocked"] is True
    assert "blocked_target_prefix:core/runtime" in result["reason"]
    assert result["rollback_performed"] is False
    assert readme.read_text(encoding="utf-8") == before_readme
    assert not (tmp_path / "core/runtime/phase2_blocked.py").exists()


def test_evidence_and_result_include_all_target_files(tmp_path: Path) -> None:
    _readme, _package_file = _seed_allowed_files(tmp_path)

    response = _run_multi_edit(
        tmp_path,
        package_id="phase2_evidence_targets",
        edits=[
            {
                "operation": "append_file",
                "target_path": "README.md",
                "content": "\nEvidence README marker.\n",
                "verify_contains": "Evidence README marker.",
            },
            {
                "operation": "write_file",
                "target_path": "core/tasks/work_package_phase2_target.py",
                "content": "VALUE = 'evidence'\n",
                "verify_contains": "VALUE = 'evidence'",
            },
        ],
    )

    result = response["work_package_result"]
    evidence = _read_json(tmp_path, result["evidence_path"])
    final = _read_json(tmp_path, result["result_path"])
    expected_targets = ["README.md", "core/tasks/work_package_phase2_target.py"]

    assert result["target_files"] == expected_targets
    assert evidence["target_files"] == expected_targets
    assert final["target_files"] == expected_targets
    assert final["changed_files"] == expected_targets
    assert final["rollback_performed"] is False
