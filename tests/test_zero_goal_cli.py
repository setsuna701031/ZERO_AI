import json

from cli.zero_goal import main

NOW = "2026-07-13T00:00:00Z"


def invoke(tmp_path, capsys, *args):
    code = main([*args, "--workspace-root", str(tmp_path), "--json", "--now", NOW]); captured = capsys.readouterr(); return code, json.loads(captured.out or captured.err)


def test_create_list_show_milestones_preview_and_json(tmp_path, capsys):
    code, goal = invoke(tmp_path, capsys, "create", "完成一個簡單網站，包含首頁、樣式與驗證")
    assert code == 0; goal_id = goal["goal_id"]
    assert invoke(tmp_path, capsys, "list")[1][0]["goal_id"] == goal_id
    assert invoke(tmp_path, capsys, "show", goal_id)[1]["goal_status"] == "ready"
    assert len(invoke(tmp_path, capsys, "milestones", goal_id)[1]) == 6
    preview_root = tmp_path / "preview"; preview_root.mkdir()
    preview = main(["preview", "完成一個簡單網站", "--workspace-root", str(tmp_path), "--target-root", str(preview_root), "--json", "--now", NOW]); value = json.loads(capsys.readouterr().out)
    assert preview == 0 and value["prepare_only"] and value["target_mutated"] is False and not any(preview_root.iterdir())


def test_run_approve_deny_pause_resume_stop_cancel_and_replan_commands(tmp_path, capsys):
    _, goal = invoke(tmp_path, capsys, "create", "完成一個簡單網站，包含首頁、樣式與驗證"); goal_id = goal["goal_id"]
    code, run = invoke(tmp_path, capsys, "run", goal_id, "--max-milestones", "1", "--max-missions", "1"); assert code == 3 and run["goal_status"] == "waiting_for_approval"
    milestone_id = run["progress"]["waiting_approval_milestones"][0]
    code, approved = invoke(tmp_path, capsys, "approve", goal_id, milestone_id, "--operator-id", "operator"); assert code == 0 and approved["goal_status"] in {"partially_completed", "ready"}
    assert invoke(tmp_path, capsys, "pause", goal_id)[0] == 5
    assert invoke(tmp_path, capsys, "resume", goal_id)[0] == 0
    assert invoke(tmp_path, capsys, "cancel", goal_id)[1]["goal_status"] == "cancelled"
    other = tmp_path / "other"; other.mkdir(); _, second = invoke(other, capsys, "create", "建立文件專案")
    assert invoke(other, capsys, "stop", second["goal_id"])[0] == 5


def test_deny_replan_status_and_interactive_exit(tmp_path, capsys, monkeypatch):
    _, goal = invoke(tmp_path, capsys, "create", "完成一個簡單網站，包含首頁、樣式與驗證"); goal_id = goal["goal_id"]
    _, run = invoke(tmp_path, capsys, "run", goal_id); milestone_id = run["progress"]["waiting_approval_milestones"][0]
    denied_code, denied = invoke(tmp_path, capsys, "deny", goal_id, milestone_id, "--operator-id", "operator", "--reason", "not approved")
    assert denied_code == 3 and denied["goal_status"] == "blocked"
    replanned_code, replanned = invoke(tmp_path, capsys, "replan", goal_id, "--reason", "safe retry")
    assert replanned_code == 0 and replanned["replan_count"] == 1
    assert invoke(tmp_path, capsys, "status", goal_id)[1]["goal_id"] == goal_id
    answers = iter(["goals", "exit"]); monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main([]) == 0 and "ZERO Long-Horizon Goal Manager" in capsys.readouterr().out
