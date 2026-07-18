import json
from cli.zero_engineering_mission_bootstrap import run
from tests.test_engineering_mission_bootstrap import intent
def test_bootstrap_validate_inspect_source_unchanged(tmp_path):
 p=tmp_path/"i.json";p.write_text(json.dumps(intent()),encoding="utf-8");before=p.read_bytes();v,c=run(["bootstrap",str(p)]);assert c==0
 a=tmp_path/"b.json";a.write_text(json.dumps(v),encoding="utf-8");assert run(["validate",str(a)])[1]==0 and run(["inspect",str(a)])[1]==0 and p.read_bytes()==before
