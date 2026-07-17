import json

from cli.zero_mission import main


NOW = "2026-07-13T00:00:00+00:00"
MISSION = "建立 hello.txt，內容是 hello zero，然後確認檔案存在"


def output(capsys):
    return json.loads(capsys.readouterr().out)


def test_approve_status_and_completed_resume_cli(tmp_path, capsys):
    assert main([MISSION, "--workspace-root", str(tmp_path), "--json", "--now", NOW]) == 3
    prepared = output(capsys)
    session_id = prepared["session_reference"]["session_id"]
    assert main(["--approve", session_id, "--workspace-root", str(tmp_path), "--operator-id", "local-operator", "--json", "--now", NOW]) == 0
    approved = output(capsys)
    assert approved["mission_status"] == approved["session_status"] == approved["execution_status"] == "completed"
    assert approved["completed_at"] is not None

    assert main(["--status", session_id, "--workspace-root", str(tmp_path), "--json", "--now", NOW]) == 0
    status = output(capsys)
    assert status["mission_status"] == status["session_status"] == "completed"
    assert status["approval_status"] == status["plan_status"] == "approved"
    assert status["completed_goal_count"] == 2 and status["waiting_goal_count"] == 0

    target = tmp_path / "hello.txt"
    before = target.stat().st_mtime_ns
    assert main(["--resume", session_id, "--workspace-root", str(tmp_path), "--json", "--now", NOW]) == 0
    resumed = output(capsys)
    assert resumed["status"] == resumed["session_status"] == "completed"
    assert resumed["mutation_performed"] is False and resumed["replayed"] is False
    assert target.stat().st_mtime_ns == before

