from __future__ import annotations

import json
from pathlib import Path

from core.runtime.runtime_natural_task_intake import RuntimeNaturalTaskIntake


def _write_activity(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {"goal": "create workspace/example.txt", "status": "completed", "ok": True,
         "changed_files": ["workspace/example.txt"], "denial_reason": ""},
        {"goal": "create workspace/example.txt", "status": "failed", "ok": False,
         "changed_files": [], "denial_reason": "validation_failed"},
    ]
    path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")


def test_intake_injects_advice_without_modifying_requested_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_activity(workspace / "operator_activity" / "activity.jsonl")
    result = RuntimeNaturalTaskIntake(
        workspace_root=workspace / "operator_intake"
    ).accept(
        "create workspace/example.txt with content hello",
        mode="controlled",
        target_root=".",
    )

    package = json.loads(Path(result["package_path"]).read_text(encoding="utf-8"))
    intake_record = json.loads(Path(result["intake_path"]).read_text(encoding="utf-8"))
    advice = result["decision_advice"]

    assert result["ok"] is True
    assert package["requested_changes"] == result["package"]["requested_changes"]
    assert package["metadata"]["memory_context"] == result["memory_context"]
    assert package["metadata"]["decision_advice"] == advice
    assert intake_record["decision_advice"] == advice
    assert advice["recommended_paths"] == ["workspace/example.txt"]
    assert advice["risk_flags"] == ["validation_failure_risk"]
    assert advice["read_only"] is True
    assert advice["decision_authority"] is False
    assert advice["requested_changes_modified"] is False


def test_chinese_create_file_package_remains_executable_shape(tmp_path: Path) -> None:
    result = RuntimeNaturalTaskIntake(
        workspace_root=tmp_path / "workspace" / "operator_intake"
    ).accept(
        "在 workspace 建立 advisor_check.txt，內容寫入 verified",
        mode="controlled",
        target_root=".",
    )
    changes = result["package"]["requested_changes"]

    assert result["ok"] is True
    assert changes
    assert changes[0]["operation"] == "create_file"
    assert changes[0]["target_path"] == "workspace/advisor_check.txt"
    assert result["package"]["metadata"]["decision_advice"]["decision_authority"] is False
