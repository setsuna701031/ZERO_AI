import json
from cli.zero_capability_strategy_runtime_integration_wiring import run
from tests.test_runtime_capability_strategy_runtime_integration_wiring import decision
def test_cli_wire_validate_inspect_and_source_unchanged(tmp_path):
 p=tmp_path/"source.json";p.write_text(json.dumps(decision()),encoding="utf-8");before=p.read_bytes();out,code=run(["wire",str(p)]);assert code==0
 a=tmp_path/"artifact.json";a.write_text(json.dumps(out),encoding="utf-8");assert run(["validate",str(a)])[1]==0 and run(["inspect",str(a)])[0]["status"]=="wired" and p.read_bytes()==before
def test_cli_invalid_json_missing_and_unsupported(tmp_path):
 bad=tmp_path/"bad.json";bad.write_text("{",encoding="utf-8");assert run(["wire",str(bad)])[1]==2 and run(["wire",str(tmp_path/"missing")])[1]==2
 empty=tmp_path/"empty.json";empty.write_text("{}",encoding="utf-8");assert run(["validate",str(empty)])[1]!=0
