import json

from cli.zero_mission import main

NOW="2026-07-13T00:00:00+00:00"


def start(tmp_path,capsys):
    assert main(["create hello.txt with content hello zero","--workspace-root",str(tmp_path),"--json","--now",NOW])==3
    return json.loads(capsys.readouterr().out)


def test_show_plan_approve_and_json_execution(tmp_path,capsys):
    artifact=start(tmp_path,capsys);session=artifact["session_reference"]["session_id"]
    assert main(["--show-plan",session,"--workspace-root",str(tmp_path),"--json","--now",NOW])==0
    plan=json.loads(capsys.readouterr().out);assert plan["target_paths"]==["hello.txt"]
    assert main(["--approve",session,"--workspace-root",str(tmp_path),"--operator-id","local-operator","--json","--now",NOW])==0
    result=json.loads(capsys.readouterr().out);assert result["mission_status"]=="completed" and (tmp_path/"hello.txt").read_text()=="hello zero"


def test_deny_returns_three_and_never_mutates(tmp_path,capsys):
    artifact=start(tmp_path,capsys);session=artifact["session_reference"]["session_id"]
    assert main(["--deny",session,"--workspace-root",str(tmp_path),"--operator-id","op","--reason","test denial","--json","--now",NOW])==3
    assert json.loads(capsys.readouterr().out)["approval_status"]=="denied" and not (tmp_path/"hello.txt").exists()
