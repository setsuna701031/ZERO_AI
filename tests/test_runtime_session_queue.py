from __future__ import annotations

import copy
import json

import pytest

from core.runtime.runtime_end_to_end_orchestrator import create_runtime_session
from core.runtime.runtime_session_queue import (create_scheduler_state, enqueue_session, load_scheduler_state,
    ordered_entries, save_scheduler_state, validate_scheduler_state)

NOW = "2026-07-12T00:00:00+00:00"

def session_file(tmp_path, name, targets=None):
    target = tmp_path / f"target-{name}"; target.mkdir(); workspace = tmp_path / f"workspace-{name}"; workspace.mkdir(); path = tmp_path / f"{name}.json"
    from core.runtime.runtime_operator_session import save_runtime_session
    session = create_runtime_session({"text": name, "target_files": targets or ["a.py"]}, target_root=target, workspace_root=workspace, now=NOW)
    save_runtime_session(session, path); return path, session, target, workspace

def test_empty_enqueue_deterministic_duplicate_and_projection(tmp_path):
    state = create_scheduler_state(state_path=tmp_path / "state.json", now=NOW); assert ordered_entries(state) == []
    path, session, target, workspace = session_file(tmp_path, "one"); original = copy.deepcopy(state)
    result = enqueue_session(state, path, priority="normal", target_root=target, workspace_root=workspace, now=NOW)
    assert state == original and result["entries"][0]["session_id"] == session["session_id"]
    assert enqueue_session(result, path, now=NOW) == result
    assert result["waiting_operator_sessions"][0]["required_action"] == "operator_approval"

def test_priority_fifo_and_invalid_priority(tmp_path):
    state = create_scheduler_state(state_path=tmp_path / "state.json", now=NOW)
    values = [session_file(tmp_path, name) for name in ("one", "two", "three")]
    state = enqueue_session(state, values[0][0], priority="normal", now=NOW)
    state = enqueue_session(state, values[1][0], priority="high", now=NOW)
    state = enqueue_session(state, values[2][0], priority="normal", now=NOW)
    assert [item["session_id"] for item in ordered_entries(state)] == [values[1][1]["session_id"], values[0][1]["session_id"], values[2][1]["session_id"]]
    with pytest.raises(ValueError, match="invalid_priority"): enqueue_session(state, values[0][0], priority=1000, now=NOW)

def test_persistence_bom_tamper_and_duplicate_sequence(tmp_path):
    state = create_scheduler_state(state_path=tmp_path / "state.json", now=NOW); path = tmp_path / "state.json"; save_scheduler_state(state, path)
    path.write_text("\ufeff" + path.read_text(encoding="utf-8"), encoding="utf-8"); assert load_scheduler_state(path)["scheduler_id"] == state["scheduler_id"]
    value = json.loads(path.read_text(encoding="utf-8-sig")); value["scheduler_status"] = "tampered"; path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="scheduler_fingerprint_mismatch"): load_scheduler_state(path)
    first = create_scheduler_state(state_path=path, now=NOW); first["entries"] = [{"session_id":"a","sequence_number":1},{"session_id":"b","sequence_number":1}]
    assert "duplicate_sequence_number" in validate_scheduler_state(first)

