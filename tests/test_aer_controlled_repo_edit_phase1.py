from __future__ import annotations

import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.planning.planner import Planner


def _run_aer_package(
    repo_root: Path,
    *,
    package_id: str,
    target_path: str,
    content: str,
    operation: str = "append_file",
    verify_contains: str | None = None,
    approval: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "task_type": "aer_task",
        "repo_root": str(repo_root),
        "task_id": package_id,
        "goal": f"Read {target_path}, apply controlled edit, verify result",
        "operation": operation,
        "target_path": target_path,
        "content": content,
        "approval": approval,
    }
    if verify_contains is not None:
        payload["verify_contains"] = verify_contains
    return AgentLoop(planner=Planner(), repo_root=str(repo_root)).run(json.dumps(payload))


def _read_json(repo_root: Path, relative_path: str) -> dict[str, object]:
    return json.loads((repo_root / relative_path).read_text(encoding="utf-8"))


def test_aer_controlled_repo_edit_success_appends_readme(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Demo\n", encoding="utf-8")

    response = _run_aer_package(
        tmp_path,
        package_id="phase1_readme_append",
        target_path="README.md",
        content="\n## Controlled AER Test\n\nPhase 1 controlled write passed.\n",
        verify_contains="Phase 1 controlled write passed.",
    )

    result = response["work_package_result"]
    assert response["ok"] is True
    assert result["ok"] is True
    assert result["task_id"] == "phase1_readme_append"
    assert result["package_id"] == "phase1_readme_append"
    assert result["target_file"] == "README.md"
    assert result["verification_result"]["ok"] is True
    assert result["evidence_path"]
    assert result["result_path"]
    assert "Phase 1 controlled write passed." in readme.read_text(encoding="utf-8")

    evidence = _read_json(tmp_path, result["evidence_path"])
    final = _read_json(tmp_path, result["result_path"])
    audit = _read_json(tmp_path, result["audit_path"])
    assert evidence["controlled_repo_write"]["applied_to_workspace"] is True
    assert evidence["verification_result"]["ok"] is True
    assert final["ok"] is True
    assert final["target_file"] == "README.md"
    assert final["verification_result"]["ok"] is True
    assert audit["ok"] is True


def test_aer_controlled_repo_edit_protected_file_blocked(tmp_path: Path) -> None:
    response = _run_aer_package(
        tmp_path,
        package_id="phase1_protected_blocked",
        target_path="core/runtime/protected.py",
        content="bad\n",
        operation="write_file",
    )

    result = response["work_package_result"]
    assert response["ok"] is False
    assert result["ok"] is False
    assert result["blocked"] is True
    assert "blocked_target_prefix:core/runtime" in result["reason"]
    assert result["target_file"] == "core/runtime/protected.py"
    assert not (tmp_path / "core/runtime/protected.py").exists()


def test_aer_controlled_repo_edit_verification_failure_path(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Demo\n", encoding="utf-8")

    response = _run_aer_package(
        tmp_path,
        package_id="phase1_verify_fail",
        target_path="README.md",
        content="\n## Controlled AER Test\n\nActual text.\n",
        verify_contains="missing verification marker",
    )

    result = response["work_package_result"]
    assert response["ok"] is False
    assert result["ok"] is False
    assert result["reason"] == "verification_failed"
    assert result["verification_result"]["ok"] is False
    assert result["verification_result"]["reason"] == "expected_text_missing"
    assert "Actual text." in readme.read_text(encoding="utf-8")


def test_aer_controlled_repo_edit_evidence_generated(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    response = _run_aer_package(
        tmp_path,
        package_id="phase1_evidence",
        target_path="README.md",
        content="\nEvidence marker.\n",
        verify_contains="Evidence marker.",
    )

    result = response["work_package_result"]
    for key in ("audit_path", "evidence_path", "result_path"):
        assert result[key]
        assert (tmp_path / result[key]).exists()


def test_aer_controlled_repo_edit_result_visible_to_caller(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    response = _run_aer_package(
        tmp_path,
        package_id="phase1_visible_result",
        target_path="README.md",
        content="\nVisible result marker.\n",
        verify_contains="Visible result marker.",
    )

    assert response["result_path"] == response["work_package_result"]["result_path"]
    assert response["execution"]["last_result"]["result_path"] == response["result_path"]
    final = _read_json(tmp_path, response["result_path"])
    assert final["task_id"] == "phase1_visible_result"
    assert final["evidence_path"] == response["evidence_path"]
