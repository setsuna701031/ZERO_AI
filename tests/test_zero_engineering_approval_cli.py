import json
from cli.zero_engineering_approval import STAGES,run
from tests.test_engineering_approval_intake import review_closure
def test_cli_all_stages_are_canonical(tmp_path):
 p=tmp_path/"review.json";p.write_text(json.dumps(review_closure()),encoding="utf-8")
 for stage in STAGES:
  value,code=run([str(p),"--stage",stage]);assert code==0 and "error" not in value
def test_cli_invalid_json(tmp_path):
 p=tmp_path/"bad.json";p.write_text("{",encoding="utf-8");assert run([str(p)])[1]==2
