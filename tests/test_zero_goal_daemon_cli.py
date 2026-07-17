import json

from cli.zero_goal import main

NOW = "2026-07-13T00:00:00Z"


def call(tmp_path, capsys, *args):
    code = main([*args, "--workspace-root", str(tmp_path), "--json", "--now", NOW]); captured = capsys.readouterr(); return code, json.loads(captured.out or captured.err)


def test_daemon_once_max_cycles_status_and_json(tmp_path, capsys):
    assert call(tmp_path, capsys, "create", "建立文件專案")[0] == 0
    code, once = call(tmp_path, capsys, "daemon", "--once"); assert code == 0 and once["daemon_status"] == "stopped" and once["cycle_count"] == 1
    code, multiple = call(tmp_path, capsys, "daemon", "--max-cycles", "2"); assert code == 0 and multiple["cycle_count"] == 3
    code, status = call(tmp_path, capsys, "daemon-status"); assert code == 0 and status["contract"] == "zero.agent.goal_daemon.v1"
    assert status["last_cycle_identity"] and status["configuration_fingerprint"] and status["waiting_approval_count"] == 1
