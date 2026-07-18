import json
from cli.zero_engineering_repository_analysis_request import run
from tests.test_engineering_mission_bootstrap import bootstrap
def test_prepare_validate_inspect_without_analysis(tmp_path):
 p=tmp_path/"b.json";p.write_text(json.dumps(bootstrap()),encoding="utf-8");v,c=run(["prepare",str(p)]);assert c==0 and v["boundary"]["repository_access"] is False
 a=tmp_path/"a.json";a.write_text(json.dumps(v),encoding="utf-8");assert run(["validate",str(a)])[1]==0 and run(["inspect",str(a)])[1]==0
