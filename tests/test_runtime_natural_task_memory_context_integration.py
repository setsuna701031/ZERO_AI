from __future__ import annotations

import json
from pathlib import Path

from core.runtime.runtime_natural_task_intake import RuntimeNaturalTaskIntake


def _write_activity(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in records
        )
        + "\n",
        encoding="utf-8",
    )


def test_intake_injects_read_only_activity_memory_context(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    activity_path = workspace / "operator_activity" / "activity.jsonl"
    _write_activity(
        activity_path,
        [
            {
                "goal": "在 workspace 建立 example.txt，內容寫入 old",
                "status": "completed",
                "ok": True,
                "changed_files": ["workspace/example.txt"],
                "denial_reason": "",
                "recorded_at": "2026-07-10T05:15:17+00:00",
            },
            {
                "goal": "在 workspace 建立 example.txt，內容寫入 old",
                "status": "failed",
                "ok": False,
                "changed_files": [],
                "denial_reason": "validation_failed",
                "recorded_at": "2026-07-10T05:14:17+00:00",
            },
        ],
    )

    result = RuntimeNaturalTaskIntake(
        workspace_root=workspace / "operator_intake"
    ).accept(
        "在 workspace 建立 example.txt，內容寫入 new",
        mode="controlled",
        target_root=".",
    )

    assert result["ok"] is True
    assert result["memory_context_injected"] is True
    assert result["memory_context_read_only"] is True

    memory_context = result["memory_context"]
    assert memory_context["memory_status"] == "context_available"
    assert memory_context["experience_count"] == 2
    assert memory_context["successful_paths"] == [
        "workspace/example.txt"
    ]
    assert memory_context["prior_denial_reasons"] == [
        "validation_failed"
    ]
    assert memory_context["read_only"] is True
    assert memory_context["decision_authority"] is False

    package = json.loads(
        Path(result["package_path"]).read_text(encoding="utf-8")
    )
    assert package["schema"] == "zero.runtime.operator_package.v1"
    assert package["metadata"]["memory_context"] == memory_context
    assert "runtime_operator_package" not in package
    assert "package" not in package


def test_intake_injects_empty_context_without_activity_log(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"

    result = RuntimeNaturalTaskIntake(
        workspace_root=workspace / "operator_intake"
    ).accept(
        "在 workspace 建立 new.txt，內容寫入 first",
        mode="controlled",
        target_root=".",
    )

    memory_context = result["memory_context"]
    assert result["ok"] is True
    assert memory_context["memory_status"] == "empty"
    assert memory_context["experience_count"] == 0
    assert memory_context["successful_paths"] == []
    assert memory_context["prior_denial_reasons"] == []

    package = json.loads(
        Path(result["package_path"]).read_text(encoding="utf-8")
    )
    assert package["schema"] == "zero.runtime.operator_package.v1"
    assert package["metadata"]["memory_context"]["read_only"] is True
    assert (
        package["metadata"]["memory_context"]["decision_authority"]
        is False
    )
