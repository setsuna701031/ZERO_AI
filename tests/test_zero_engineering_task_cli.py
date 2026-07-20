import json
from cli.zero_engineering_task import main

def test_cli_create_invalid_and_inspect(tmp_path, capsys):
    assert main(['create','--repo-root',str(tmp_path),'--json',json.dumps({'repository_identity':{'id':'r'},'requested_outcome':'x'})])==0
    out=json.loads(capsys.readouterr().out); tid=out['task_id']
    assert main(['inspect','--repo-root',str(tmp_path),'--task-id',tid])==0
    assert json.loads(capsys.readouterr().out)['task_id']==tid
    assert main(['create','--repo-root',str(tmp_path),'--json','{'])==2
