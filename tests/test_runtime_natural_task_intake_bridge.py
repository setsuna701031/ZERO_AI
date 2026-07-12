from __future__ import annotations

import json
from pathlib import Path

from cli.zero_natural_task import run_natural_task
from core.runtime.runtime_natural_task_intake import (
    RUNTIME_NATURAL_TASK_INTAKE_SCHEMA,
    RuntimeNaturalTaskIntake,
)


def _read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_natural_task_intake_preserves_goal_and_materializes_package(tmp_path: Path) -> None:
    intake = RuntimeNaturalTaskIntake(workspace_root=tmp_path / "operator_intake")

    result = intake.accept(
        "create a file and run validation",
        mode="controlled",
        target_root=".",
    )

    assert result["schema"] == RUNTIME_NATURAL_TASK_INTAKE_SCHEMA
    assert result["ok"] is True
    assert result["goal"] == "create a file and run validation"
    assert result["requested_mode"] == "controlled"
    assert result["package_generated"] is True
    assert result["validation_required"] is True
    assert result["rollback_required"] is True

    intake_record = _read_json(result["intake_path"])
    package = _read_json(result["package_path"])

    assert intake_record["goal"] == "create a file and run validation"
    assert intake_record["status"] == "accepted"
    assert package["schema"] == "zero.runtime.operator_package.v1"
    assert package["requested_mode"] == "controlled"
    assert package["validation_required"] is True
    assert package["rollback_required"] is True
    assert package["natural_task_intake_id"] == result["intake_id"]


def test_zero_natural_task_cli_bridge_runs_operator_console(tmp_path: Path) -> None:
    result = run_natural_task(
        "update docs without bypassing validation",
        controlled=True,
        target_root=".",
        workspace_root=tmp_path / "operator_intake",
    )

    assert result["schema"] == "zero.natural_task_cli.v1"
    assert result["ok"] is True
    assert result["package_generated"] is True
    assert result["validation_required"] is True
    assert result["rollback_required"] is True
    assert result["operator_console_available"] is True
    assert Path(result["intake_path"]).exists()
    assert Path(result["package_path"]).exists()
    assert Path(result["result_path"]).exists()

    package = _read_json(result["package_path"])
    operator_result = _read_json(result["result_path"])

    assert package["requested_mode"] == "controlled"
    assert package["validation_required"] is True
    assert package["rollback_required"] is True
    assert operator_result["ok"] is True
    assert operator_result["command"] == "run"


def test_natural_task_intake_does_not_expose_executor_bypass() -> None:
    source = Path("core/runtime/runtime_natural_task_intake.py").read_text(encoding="utf-8")
    forbidden = (
        "subprocess",
        "os.system",
        "exec(",
        "eval(",
        "git ",
        "RuntimeOperatorService(",
        "StepExecutor(",
    )
    for token in forbidden:
        assert token not in source
