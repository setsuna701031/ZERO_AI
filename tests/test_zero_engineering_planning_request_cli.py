import json
from cli.zero_engineering_planning_request import run
from tests.test_engineering_repository_analysis_request import analysis
def test_plan_request_validate_inspect_without_planner(tmp_path):
 p=tmp_path/"a.json";p.write_text(json.dumps(analysis()),encoding="utf-8");v,c=run(["plan-request",str(p)]);assert c==0 and v["boundary"]["planning_started"] is False
 x=tmp_path/"p.json";x.write_text(json.dumps(v),encoding="utf-8");assert run(["validate",str(x)])[1]==0 and run(["inspect",str(x)])[1]==0
