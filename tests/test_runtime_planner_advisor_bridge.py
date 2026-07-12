from __future__ import annotations

import copy
import json
from pathlib import Path

from core.runtime.runtime_natural_task_intake import RuntimeNaturalTaskIntake
from core.runtime.runtime_planner_advisor_bridge import (
    build_planner_advisor_bridge,
)


def test_success_paths_risks_and_rankings_do_not_modify_changes() -> None:
    changes = [
        {"change_id": "one", "target_path": "workspace/good.txt", "operation": "create_file"},
        {"change_id": "two", "target_path": "workspace/other.txt", "operation": "create_file"},
    ]
    before = copy.deepcopy(changes)
    bridge = build_planner_advisor_bridge("create files", changes, {
        "previous_success_available": True,
        "recommended_paths": ["workspace/good.txt"],
        "risk_flags": ["validation_failure_risk", "unsafe_path_risk"],
    })

    assert bridge["schema"] == "zero.runtime.planner_advisor_bridge.v1"
    assert bridge["preferred_paths"] == ["workspace/good.txt"]
    assert bridge["avoid_risk_flags"] == [
        "validation_failure_risk", "unsafe_path_risk"
    ]
    assert bridge["candidate_rankings"] == [
        {"change_id": "one", "ranking": "preferred"},
        {"change_id": "two", "ranking": "caution"},
    ]
    assert changes == before
    assert bridge["read_only"] is True
    assert bridge["decision_authority"] is False
    assert bridge["requested_changes_modified"] is False


def test_empty_advice_is_safe_and_neutral() -> None:
    bridge = build_planner_advisor_bridge(
        "new task", [{"change_id": "one", "target_path": "a.txt"}], {}
    )

    assert bridge["ok"] is True
    assert bridge["bridge_status"] == "no_hints"
    assert bridge["preferred_paths"] == []
    assert bridge["avoid_risk_flags"] == []
    assert bridge["candidate_rankings"] == [
        {"change_id": "one", "ranking": "neutral"}
    ]


def test_intake_preserves_all_advisory_metadata(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    activity_path = workspace / "operator_activity" / "activity.jsonl"
    activity_path.parent.mkdir(parents=True)
    records = [
        {"goal": "create workspace/example.txt", "status": "completed", "ok": True,
         "changed_files": ["workspace/example.txt"], "denial_reason": ""},
        {"goal": "create workspace/example.txt", "status": "failed", "ok": False,
         "changed_files": [], "denial_reason": "validation_failed"},
    ]
    activity_path.write_text(
        "\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8"
    )

    result = RuntimeNaturalTaskIntake(
        workspace_root=workspace / "operator_intake"
    ).accept("create workspace/example.txt with content hello")
    package = result["package"]
    metadata = package["metadata"]
    bridge = result["planner_advisor_bridge"]

    assert metadata["memory_context"] == result["memory_context"]
    assert metadata["decision_advice"] == result["decision_advice"]
    assert metadata["planner_advisor_bridge"] == bridge
    assert result["intake_record"]["planner_advisor_bridge"] == bridge
    assert bridge["candidate_rankings"][0]["ranking"] == "preferred"
    assert bridge["requested_changes_modified"] is False
