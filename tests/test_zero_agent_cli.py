import json

from cli.zero_agent import main


NOW = "2026-07-13T00:00:00+00:00"


def payload(capsys): return json.loads(capsys.readouterr().out)


def call(tmp_path, capsys, *args):
    code = main([*args, "--workspace-root", str(tmp_path), "--json", "--now", NOW]); return code, payload(capsys)


def test_add_list_show_priority_cancel_json(tmp_path, capsys):
    code, added = call(tmp_path, capsys, "add", "建立 hello.txt，內容是 hello zero", "--priority", "high")
    assert code == 0 and added["priority"] == "high"
    assert call(tmp_path, capsys, "show", added["entry_id"])[1]["original_input"].startswith("建立")
    assert call(tmp_path, capsys, "priority", added["entry_id"], "low")[1]["priority"] == "low"
    assert len(call(tmp_path, capsys, "list", "--status", "pending")[1]) == 1
    assert call(tmp_path, capsys, "cancel", added["entry_id"])[1]["status"] == "cancelled"


def test_run_status_and_approve_cli(tmp_path, capsys):
    code, added = call(tmp_path, capsys, "add", "create hello.txt with content hello zero and then verify it")
    run_code, result = call(tmp_path, capsys, "run", "--max-missions", "1", "--max-iterations", "3")
    assert run_code == 3 and result["waiting_approval"] == 1
    approve_code, completed = call(tmp_path, capsys, "approve", added["entry_id"], "--operator-id", "operator")
    assert approve_code == 0 and completed["status"] == "completed"
    assert call(tmp_path, capsys, "status")[1]["missions_completed"] == 1


def test_pause_resume_stop_exit_codes(tmp_path, capsys):
    assert call(tmp_path, capsys, "pause")[0] == 5
    assert call(tmp_path, capsys, "resume")[0] == 0
    assert call(tmp_path, capsys, "stop")[0] == 5


def test_deny_cli_returns_blocked_without_effect(tmp_path, capsys):
    _, added = call(tmp_path, capsys, "add", "create hello.txt with content hello zero")
    call(tmp_path, capsys, "run", "--max-missions", "1")
    code, denied = call(tmp_path, capsys, "deny", added["entry_id"], "--operator-id", "operator", "--reason", "denied")
    assert code == 3 and denied["status"] == "blocked" and not (tmp_path / "hello.txt").exists()


def test_interactive_basic_commands(tmp_path, monkeypatch, capsys):
    commands = iter(["add read README.md", "missions", "status", "exit"]); monkeypatch.chdir(tmp_path); monkeypatch.setattr("builtins.input", lambda _: next(commands))
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "ZERO Autonomous Agent" in output and "Entry ID:" in output
