from __future__ import annotations

import copy
import json

import pytest

from core.runtime.runtime_end_to_end_orchestrator import create_runtime_session
from core.runtime.runtime_operator_session import load_runtime_session, save_runtime_session, transition, validate_session

NOW = "2026-07-12T00:00:00+00:00"

def make(tmp_path):
    target = tmp_path / "target"; target.mkdir(exist_ok=True); workspace = tmp_path / "workspace"; workspace.mkdir(exist_ok=True)
    return create_runtime_session({"text": "repair", "target_files": ["a.py"]}, target_root=target, workspace_root=workspace, now=NOW)

def test_deterministic_create_and_transition_table(tmp_path):
    first = make(tmp_path); second = make(tmp_path)
    assert first["session_id"] == second["session_id"]
    assert first["session_status"] == "waiting_for_operator_approval"
    with pytest.raises(ValueError, match="invalid_transition"):
        transition(first, "completed", now=NOW)

def test_save_load_bom_and_tamper_detection(tmp_path):
    session = make(tmp_path); path = tmp_path / "session.json"; save_runtime_session(session, path)
    assert load_runtime_session(path) == session
    path.write_text("\ufeff" + path.read_text(encoding="utf-8"), encoding="utf-8")
    assert load_runtime_session(path)["session_id"] == session["session_id"]
    value = json.loads(path.read_text(encoding="utf-8-sig")); value["current_phase"] = "tampered"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="session_fingerprint_mismatch"): load_runtime_session(path)

def test_artifact_and_root_mismatch_and_input_unchanged(tmp_path):
    session = make(tmp_path); original = copy.deepcopy(session)
    changed = copy.deepcopy(session); changed["artifacts"]["proposal"]["proposal_id"] = "bad"
    assert any("artifact_fingerprint_mismatch" in reason for reason in validate_session(changed))
    other = tmp_path / "other"; other.mkdir()
    assert "target_root_mismatch" in validate_session(session, target_root=other)
    assert session == original
