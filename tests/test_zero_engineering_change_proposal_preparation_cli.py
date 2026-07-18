import json
from cli.zero_engineering_change_proposal_preparation import run
from tests.test_engineering_planning_request import planning
def test_prepare_validate_inspect_without_proposal(tmp_path):
 p=tmp_path/"p.json";p.write_text(json.dumps(planning()),encoding="utf-8");v,c=run(["prepare",str(p)]);assert c==0 and v["boundary"]["proposal_created"] is False
 x=tmp_path/"c.json";x.write_text(json.dumps(v),encoding="utf-8");assert run(["validate",str(x)])[1]==0 and run(["inspect",str(x)])[1]==0
