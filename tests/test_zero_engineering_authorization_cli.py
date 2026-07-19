import json
from cli.zero_engineering_authorization import STAGES,run
from tests.test_engineering_authorization_intake import approval_closure
def test_cli_all_stages(tmp_path):
 p=tmp_path/"approval.json";p.write_text(json.dumps(approval_closure()),encoding="utf-8")
 for stage in STAGES:
  value,code=run([str(p),"--stage",stage]);assert code==0 and "error" not in value
def test_cli_invalid_json(tmp_path):
 p=tmp_path/"bad.json";p.write_text("{",encoding="utf-8");assert run([str(p)])[1]==2
