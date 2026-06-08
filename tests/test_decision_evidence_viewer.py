from __future__ import annotations

import inspect
import json
from pathlib import Path

from cli.control_cli import main as control_main
from core.control.decision_evidence_viewer import DecisionEvidenceViewer


def _write_store(repo_root: Path) -> Path:
    path = repo_root / "runtime" / "evidence" / "decision_evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "zero.decision_evidence.store.v1",
        "updated_at": 123.0,
        "records": [
            {
                "decision_id": "decision_a",
                "goal_id": "goal_1",
                "task_id": "task_1",
                "source_stage": "engineering_goal_loop",
                "observed_event": {"runtime_state": "replan"},
                "outcome_class": "recoverable_failure",
                "decision": "replan",
                "decision_reason": "runtime_outcome_recoverable_failure",
                "next_action": "request_replan",
                "evidence_refs": ["evidence_1"],
                "created_at": 2.0,
                "links": {
                    "cycle_index": 1,
                    "continuation_goal_id": "",
                    "replan_goal_id": "goal_1_replan",
                },
            },
            {
                "decision_id": "decision_b",
                "goal_id": "goal_2",
                "task_id": "task_2",
                "source_stage": "engineering_goal_loop",
                "observed_event": {"runtime_state": "running"},
                "outcome_class": "partial_success",
                "decision": "continue",
                "decision_reason": "runtime_outcome_partial_success",
                "next_action": "create_followup_goal",
                "created_at": 1.0,
                "links": {
                    "cycle_index": 0,
                    "continuation_goal_id": "goal_2_continuation",
                    "replan_goal_id": "",
                },
            },
            {
                "decision_id": "decision_missing",
                "goal_id": "goal_1",
                "task_id": "task_missing",
                "created_at": 3.0,
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_viewer_loads_persisted_decision_evidence_read_only(tmp_path: Path) -> None:
    store = _write_store(tmp_path)
    before = store.read_bytes()

    view = DecisionEvidenceViewer(tmp_path).view()

    assert view["ok"] is True
    assert view["record_count"] == 3
    assert view["records"][0]["decision_id"] == "decision_b"
    assert store.read_bytes() == before


def test_viewer_filters_by_goal_id(tmp_path: Path) -> None:
    _write_store(tmp_path)

    view = DecisionEvidenceViewer(tmp_path).view(goal_id="goal_1")

    assert view["record_count"] == 2
    assert {record["goal_id"] for record in view["records"]} == {"goal_1"}


def test_viewer_filters_by_task_id(tmp_path: Path) -> None:
    _write_store(tmp_path)

    view = DecisionEvidenceViewer(tmp_path).view(task_id="task_2")

    assert view["record_count"] == 1
    assert view["records"][0]["decision_id"] == "decision_b"


def test_viewer_exposes_reason_next_action_and_goal_loop_links(tmp_path: Path) -> None:
    _write_store(tmp_path)

    record = DecisionEvidenceViewer(tmp_path).view(task_id="task_1")["records"][0]

    assert record["timeline"]["reason"] == "runtime_outcome_recoverable_failure"
    assert record["timeline"]["next_action"] == "request_replan"
    assert record["links"]["replan_goal_id"] == "goal_1_replan"
    assert record["links"]["continuation_goal_id"] == "unavailable"


def test_viewer_does_not_fabricate_missing_fields(tmp_path: Path) -> None:
    _write_store(tmp_path)

    record = DecisionEvidenceViewer(tmp_path).view(task_id="task_missing")["records"][0]

    assert record["timeline"]["reason"] == "unavailable"
    assert record["timeline"]["next_action"] == "unavailable"
    assert record["timeline"]["observed_event"] == "unavailable"


def test_cli_command_returns_readable_output(tmp_path: Path, capsys) -> None:
    _write_store(tmp_path)

    exit_code = control_main(["--repo-root", str(tmp_path), "evidence", "--goal-id", "goal_2"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Decision Evidence" in output
    assert "records: 1" in output
    assert "observed_event" in output
    assert "outcome_class: partial_success" in output
    assert "decision: continue" in output
    assert "reason: runtime_outcome_partial_success" in output
    assert "next_action: create_followup_goal" in output
    assert "continuation_goal_id: goal_2_continuation" in output


def test_viewer_has_no_runtime_execution_or_tool_dependency() -> None:
    source = inspect.getsource(
        __import__("core.control.decision_evidence_viewer", fromlist=["DecisionEvidenceViewer"])
    )

    assert "core.runtime" not in source
    assert "core.tasks.scheduler" not in source
    assert "Scheduler" not in source
    assert "core.tools" not in source
    assert ".execute(" not in source
    assert ".tick(" not in source
    assert ".save(" not in source
