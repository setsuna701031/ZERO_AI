import json
from cli.zero_engineering_proposal import STAGES,main,run
from tests.test_engineering_proposal_intake import proposal_planning_closure
def test_cli_all_stages_and_errors(tmp_path,capsys):
 path=tmp_path/"closure.json";path.write_text(json.dumps(proposal_planning_closure(tmp_path/"repo")),encoding="utf-8")
 for stage in STAGES:assert run([str(path),"--stage",stage])[1]==0
 assert main([str(path)])==0;out=capsys.readouterr().out;assert json.loads(out)["status"]=="closed"
 bad=tmp_path/"bad.json";bad.write_text("{",encoding="utf-8");assert run([str(bad)])[1]==2
 assert run([str(path),"--stage","bad"])[1]!=0
