from pathlib import Path

from core.runtime.runtime_mission_model import load_mission
from core.runtime.runtime_mission_session import load_mission_session_state, resume_mission_session
from core.runtime.runtime_natural_language_mission_bootstrap import NaturalLanguageMissionBootstrap

NOW = "2026-07-13T00:00:00+00:00"


def test_prepare_runtime_resume_identity_and_no_duplicate_effect(tmp_path):
    bootstrap = NaturalLanguageMissionBootstrap()
    artifact = bootstrap.run("create hello.txt with content hello zero and then verify it", workspace_root=tmp_path, max_iterations=1, now=NOW)
    mission = load_mission(artifact["mission_reference"]["path"], check_expiry=False)
    session_path = artifact["session_reference"]["path"]
    before = load_mission_session_state(session_path)
    resumed = bootstrap.resume(before["session_id"], workspace_root=tmp_path, max_iterations=1, now=NOW)
    assert resumed["session_id"] == before["session_id"]
    assert resumed["resume_count"] == 1
    assert mission["goal_order"] == artifact["graph_reference"]["goal_order"]
    assert not Path(tmp_path / "hello.txt").exists()
    again = resume_mission_session(session_path, explicit=True, max_iterations=1, now=NOW)
    assert again["resume_count"] == 2 and not Path(tmp_path / "hello.txt").exists()
