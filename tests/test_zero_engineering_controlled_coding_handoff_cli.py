import json
from cli.zero_engineering_controlled_coding_handoff import run
from tests.test_engineering_change_proposal_preparation import preparation
def test_handoff_validate_inspect_without_coding(tmp_path):
 p=tmp_path/"p.json";p.write_text(json.dumps(preparation()),encoding="utf-8");v,c=run(["handoff",str(p)]);assert c==0 and v["boundary"]["coding_started"] is False
 x=tmp_path/"h.json";x.write_text(json.dumps(v),encoding="utf-8");assert run(["validate",str(x)])[1]==0 and run(["inspect",str(x)])[0]["next_stage"]=="repository_analysis_pending"
