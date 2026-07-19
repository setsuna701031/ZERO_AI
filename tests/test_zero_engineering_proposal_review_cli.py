import json
from cli.zero_engineering_proposal_review import STAGES,run
from tests.test_engineering_proposal_review_intake import sealed_closure
def test_cli_all_stages(tmp_path):
 p=tmp_path/"closure.json";p.write_text(json.dumps(sealed_closure(tmp_path)),encoding="utf-8")
 for stage in STAGES:
  value,code=run([str(p),"--stage",stage]);assert "error" not in value and code==0
def test_cli_invalid_json(tmp_path):
 p=tmp_path/"bad.json";p.write_text("{",encoding="utf-8");assert run([str(p)])[1]==2
