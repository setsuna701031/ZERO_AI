from pathlib import Path
import json

import pytest

from core.runtime.runtime_mission_model import load_mission
from core.runtime.runtime_mission_session import load_mission_session_state
from core.runtime.runtime_natural_language_mission_bootstrap import (
    bootstrap_mission, interpret_natural_language_mission,
    run_natural_language_mission,
)

NOW = "2026-07-13T00:00:00+00:00"


def test_create_file_and_verify_are_structured_dependencies(tmp_path):
    value = interpret_natural_language_mission("create hello.txt with content hello zero and then verify it", target_root=tmp_path)
    assert [item["operation"] for item in value["structured_intents"]] == ["create_file", "check_exists"]
    assert value["structured_intents"][0]["content"] == "hello zero"
    artifact = bootstrap_mission("create hello.txt with content hello zero and then verify it", workspace_root=tmp_path, now=NOW)
    mission = load_mission(artifact["mission_reference"]["path"], check_expiry=False)
    assert mission["goals"][mission["goal_order"][1]]["depends_on"] == [mission["goal_order"][0]]


@pytest.mark.parametrize(("text", "operation"), [
    ("create directory reports", "create_directory"),
    ("check whether README.md exists", "check_exists"),
    ("read README.md", "read_file"),
    ("run pytest tests/test_x.py -q", "run_tests"),
    ("建立資料夾 reports", "create_directory"),
    ("讀取 README.md", "read_file"),
])
def test_supported_baseline_intents(tmp_path, text, operation):
    assert interpret_natural_language_mission(text, target_root=tmp_path)["structured_intents"][0]["operation"] == operation


def test_unsupported_is_blocked_without_runtime_files(tmp_path):
    artifact = bootstrap_mission("please somehow improve everything", workspace_root=tmp_path, now=NOW)
    assert artifact["bootstrap_status"] == "blocked" and artifact["manual_review_required"]
    assert artifact["mission_reference"] is None


def test_prepare_is_deterministic_atomic_and_does_not_create_worker(tmp_path):
    first = bootstrap_mission("read README.md", workspace_root=tmp_path, now=NOW)
    second = bootstrap_mission("read README.md", workspace_root=tmp_path, now=NOW)
    assert first == second
    session = load_mission_session_state(first["session_reference"]["path"])
    assert not Path(session["worker_state_path"]).exists()
    assert json.loads(Path(first["artifact_path"]).read_text(encoding="utf-8"))["artifact_fingerprint"] == first["artifact_fingerprint"]


def test_traversal_and_arbitrary_command_are_rejected_or_blocked(tmp_path):
    with pytest.raises(ValueError, match="unsafe"):
        interpret_natural_language_mission("read ../secret.txt", target_root=tmp_path)
    value = interpret_natural_language_mission("run powershell Remove-Item x", target_root=tmp_path)
    assert value["supported"] is False


def test_run_enters_persisted_runtime_without_bypassing_approval(tmp_path):
    result = run_natural_language_mission("create hello.txt with content hello zero", workspace_root=tmp_path, now=NOW)
    assert result["session_status"] == "idle"
    assert not (tmp_path / "hello.txt").exists()
    session = load_mission_session_state(result["session_reference"]["path"])
    assert session["current_phase"] == "runtime_idle"
