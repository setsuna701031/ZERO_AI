from __future__ import annotations

from pathlib import Path

from core.tasks.engineering_task_runner import run_engineering_task


def _seed_allowed_files(repo_root: Path) -> tuple[Path, Path]:
    readme = repo_root / "README.md"
    target = repo_root / "core/tasks/work_package_phase5_target.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text("# Phase 5\n", encoding="utf-8")
    target.write_text("VALUE = 'original'\n", encoding="utf-8")
    return readme, target


def _engineering_payload(*, package_id: str, edits: list[dict[str, object]]) -> dict[str, object]:
    return {
        "task_type": "engineering_task",
        "task_id": package_id,
        "goal": "Run repeatable Phase 5 engineering task",
        "mode": "execute",
        "approval": True,
        "acceptance": [
            "requirement summary generated",
            "edit plan generated",
            "impact analysis generated",
            "change set generated",
            "verification result included",
        ],
        "edits": edits,
    }


def test_real_engineering_task_produces_requirement_summary(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)
    result = run_engineering_task(
        _engineering_payload(
            package_id="phase5_requirement_summary",
            edits=[
                {
                    "operation": "append_file",
                    "target_path": "README.md",
                    "content": "\nPhase 5 requirement summary marker.\n",
                    "verify_contains": "Phase 5 requirement summary marker.",
                }
            ],
        ),
        repo_root=tmp_path,
    )

    summary = result["requirement_summary"]
    assert result["ok"] is True
    assert summary["schema"] == "zero.engineering_task.requirement_summary.v1"
    assert summary["package_id"] == "phase5_requirement_summary"
    assert summary["goal"] == "Run repeatable Phase 5 engineering task"
    assert summary["target_files"] == ["README.md"]


def test_edit_plan_generated(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)
    result = run_engineering_task(
        _engineering_payload(
            package_id="phase5_edit_plan",
            edits=[
                {
                    "operation": "append_file",
                    "target_path": "README.md",
                    "content": "\nPhase 5 edit plan marker.\n",
                    "verify_contains": "Phase 5 edit plan marker.",
                }
            ],
        ),
        repo_root=tmp_path,
    )

    edit_plan = result["result_bundle"]["edit_plan"]
    assert edit_plan["schema"] == "zero.work_package.structured_edit_plan.v1"
    assert edit_plan["valid"] is True
    assert edit_plan["target_files"] == ["README.md"]


def test_impact_analysis_generated(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)
    result = run_engineering_task(
        _engineering_payload(
            package_id="phase5_impact_analysis",
            edits=[
                {
                    "operation": "write_file",
                    "target_path": "core/tasks/work_package_phase5_target.py",
                    "content": "VALUE = 'impact'\n",
                    "verify_contains": "VALUE = 'impact'",
                }
            ],
        ),
        repo_root=tmp_path,
    )

    impact = result["result_bundle"]["impact_analysis"]
    assert impact["schema"] == "zero.work_package.impact_analysis.v1"
    assert impact["valid"] is True
    assert impact["affected_modules"] == ["core/tasks"]


def test_change_set_generated(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)
    result = run_engineering_task(
        _engineering_payload(
            package_id="phase5_change_set",
            edits=[
                {
                    "operation": "append_file",
                    "target_path": "README.md",
                    "content": "\nPhase 5 change set marker.\n",
                    "verify_contains": "Phase 5 change set marker.",
                }
            ],
        ),
        repo_root=tmp_path,
    )

    change_set = result["change_set"]
    assert change_set["schema"] == "zero.work_package.change_set.v1"
    assert change_set["complete"] is True
    assert change_set["successful"] is True
    assert change_set["files"] == ["README.md"]


def test_verification_result_included(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)
    result = run_engineering_task(
        _engineering_payload(
            package_id="phase5_verification_result",
            edits=[
                {
                    "operation": "append_file",
                    "target_path": "README.md",
                    "content": "\nPhase 5 verification marker.\n",
                    "verify_contains": "Phase 5 verification marker.",
                }
            ],
        ),
        repo_root=tmp_path,
    )

    bundle = result["result_bundle"]
    assert bundle["verification_result"]["ok"] is True
    assert bundle["verification_set"]["ok"] is True
    assert bundle["change_set"]["verification_set"]["ok"] is True


def test_failed_verification_rolls_back(tmp_path: Path) -> None:
    readme, target = _seed_allowed_files(tmp_path)
    before_readme = readme.read_text(encoding="utf-8")
    before_target = target.read_text(encoding="utf-8")

    result = run_engineering_task(
        _engineering_payload(
            package_id="phase5_failed_verification_rollback",
            edits=[
                {
                    "operation": "append_file",
                    "target_path": "README.md",
                    "content": "\nTemporary Phase 5 edit.\n",
                    "verify_contains": "Temporary Phase 5 edit.",
                },
                {
                    "operation": "write_file",
                    "target_path": "core/tasks/work_package_phase5_target.py",
                    "content": "VALUE = 'temporary'\n",
                    "verify_contains": "marker intentionally absent",
                },
            ],
        ),
        repo_root=tmp_path,
    )

    bundle = result["result_bundle"]
    assert result["ok"] is False
    assert bundle["verification_result"]["ok"] is False
    assert bundle["rollback_status"]["rollback_performed"] is True
    assert bundle["rollback_status"]["ok"] is True
    assert readme.read_text(encoding="utf-8") == before_readme
    assert target.read_text(encoding="utf-8") == before_target


def test_result_bundle_visible_to_caller(tmp_path: Path) -> None:
    _seed_allowed_files(tmp_path)
    result = run_engineering_task(
        _engineering_payload(
            package_id="phase5_visible_bundle",
            edits=[
                {
                    "operation": "append_file",
                    "target_path": "README.md",
                    "content": "\nPhase 5 visible bundle marker.\n",
                    "verify_contains": "Phase 5 visible bundle marker.",
                }
            ],
        ),
        repo_root=tmp_path,
    )

    bundle = result["result_bundle"]
    assert bundle["schema"] == "zero.engineering_task.result_bundle.v1"
    assert bundle["requirement_summary"] == result["requirement_summary"]
    assert bundle["edit_plan"]
    assert bundle["impact_analysis"]
    assert bundle["change_set"]
    assert bundle["artifact_paths"]["result_path"]
    assert bundle["execution_path"]["no_new_runtime_path"] is True
    assert bundle["execution_path"]["direct_write_shortcut"] is False
