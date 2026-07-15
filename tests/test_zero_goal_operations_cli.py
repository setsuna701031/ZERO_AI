import json

from cli.zero_goal import main
from tests.goal_operations_test_support import make_waiting_goal

def test_all_operations_cli_json_commands(tmp_path, capsys):
    _, goal, _ = make_waiting_goal(tmp_path)
    for command in (["overview"], ["inspect", goal["goal_id"]], ["timeline", goal["goal_id"]], ["health"], ["pending-approvals"]):
        code = main([*command, "--workspace-root", str(tmp_path), "--json"]); captured = capsys.readouterr()
        assert code in {0, 3} and json.loads(captured.out)["contract"] == "zero.agent.goal_operations.v1" and captured.err == ""

def test_cli_unknown_goal_has_json_error_and_no_traceback(tmp_path, capsys):
    make_waiting_goal(tmp_path); code = main(["inspect", "missing", "--workspace-root", str(tmp_path), "--json"]); captured = capsys.readouterr()
    assert code == 2 and json.loads(captured.err)["error"] == "goal_not_found" and "Traceback" not in captured.err
