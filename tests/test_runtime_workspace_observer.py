from __future__ import annotations

import copy
import json
from pathlib import Path

from core.runtime.runtime_workspace_observer import RuntimeWorkspaceObserver


def test_observes_utf8_changed_file_and_summary_without_mutation(tmp_path: Path) -> None:
    target = tmp_path / "workspace" / "hello.txt"
    target.parent.mkdir()
    target.write_text("你好 observer", encoding="utf-8")
    runner_result = {
        "ok": True,
        "changed_files": ["workspace/hello.txt"],
        "validation_passed": True,
        "controlled": True,
        "requested_changes": [{"change_id": "one"}],
    }
    before = copy.deepcopy(runner_result)
    result = RuntimeWorkspaceObserver(tmp_path).observe(
        goal="unchanged goal", task_id="task-1",
        changed_files=["workspace/hello.txt"], runner_result=runner_result,
    )

    file_result = result["file_observations"][0]
    assert result["schema"] == "zero.runtime.workspace_observer.v1"
    assert result["observer_status"] == "observed"
    assert file_result["exists"] is True
    assert file_result["readable"] is True
    assert file_result["content_hash_sha256"]
    assert file_result["text_preview"] == "你好 observer"
    assert result["runner_summary"]["validation_passed"] is True
    assert runner_result == before
    assert result["goal"] == "unchanged goal"
    assert result["read_only"] is True
    assert result["mutation_allowed"] is False
    assert result["repair_allowed"] is False
    assert result["decision_authority"] is False
    assert result["requested_changes_modified"] is False


def test_binary_missing_and_oversized_are_safe(tmp_path: Path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"\xff\x00")
    (tmp_path / "large.txt").write_text("x" * 20, encoding="utf-8")
    result = RuntimeWorkspaceObserver(tmp_path, max_file_bytes=5).observe(
        goal="inspect", task_id="task",
        changed_files=["binary.bin", "large.txt", "missing.txt"],
        runner_result={},
    )
    by_path = {item["path"]: item for item in result["file_observations"]}

    assert by_path["binary.bin"]["observation_status"] == "binary"
    assert by_path["large.txt"]["observation_status"] == "oversized"
    assert by_path["large.txt"]["content_hash_sha256"] == ""
    assert by_path["missing.txt"]["observation_status"] == "missing"
    assert result["observer_status"] == "observed_with_issues"


def test_absolute_traversal_and_workspace_escape_are_denied(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    observer = RuntimeWorkspaceObserver(tmp_path)
    for path in (str(outside.resolve()), "../outside.txt"):
        result = observer.observe(
            goal="inspect", task_id="task", changed_files=[path], runner_result={}
        )
        assert result["ok"] is False
        assert result["observer_status"] == "denied_invalid_path"
        assert result["file_observations"][0]["readable"] is False


def test_symlink_escape_is_denied_when_symlink_is_available(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-link-target.txt"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        return
    result = RuntimeWorkspaceObserver(tmp_path).observe(
        goal="inspect", task_id="task", changed_files=["escape.txt"], runner_result={}
    )
    assert result["observer_status"] == "denied_invalid_path"


def test_evidence_json_parse_and_parse_error_are_recorded(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    invalid = tmp_path / "invalid.json"
    valid.write_text(json.dumps({"ok": True}), encoding="utf-8")
    invalid.write_text("{", encoding="utf-8")
    result = RuntimeWorkspaceObserver(tmp_path).observe(
        goal="inspect", task_id="task", changed_files=[],
        runner_result={
            "operator_result": {
                "governed_commit_record_path": str(valid),
                "rollback_evidence_path": str(invalid),
            }
        },
    )
    evidence = {item["evidence_type"]: item for item in result["evidence_observations"]}

    assert evidence["governed_commit_record_path"]["parsed_json"] == {"ok": True}
    assert evidence["rollback_evidence_path"]["parse_error"] == "JSONDecodeError"
    assert result["observer_status"] == "observed_with_issues"


def test_empty_changes_and_invalid_configuration() -> None:
    no_changes = RuntimeWorkspaceObserver(".").observe(
        goal="inspect", task_id="task", changed_files=[], runner_result={}
    )
    invalid = RuntimeWorkspaceObserver(".", max_file_bytes=0).observe(
        goal="inspect", task_id="task", changed_files=[], runner_result={}
    )

    assert no_changes["observer_status"] == "no_changes"
    assert invalid["observer_status"] == "denied_invalid_configuration"
    assert invalid["observation_complete"] is True
