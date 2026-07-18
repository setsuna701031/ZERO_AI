import json
from cli.zero_capability_strategy_runtime_integration_verification import run
from tests.test_runtime_capability_strategy_runtime_integration_verification import chain
def test_cli_verify_validate_inspect_and_sources_unchanged(tmp_path):
 paths=[]
 for name,value in zip(("c","d","w"),chain()):
  p=tmp_path/f"{name}.json";p.write_text(json.dumps(value),encoding="utf-8");paths.append(p)
 before=[p.read_bytes() for p in paths];out,code=run(["verify",*[str(p) for p in paths]]);assert code==0
 a=tmp_path/"v.json";a.write_text(json.dumps(out),encoding="utf-8");assert run(["validate",str(a)])[1]==0 and run(["inspect",str(a)])[0]["status"]=="verified" and [p.read_bytes() for p in paths]==before
def test_cli_invalid_json_and_missing_file(tmp_path):
 bad=tmp_path/"bad";bad.write_text("{",encoding="utf-8");assert run(["validate",str(bad)])[1]==2 and run(["validate",str(tmp_path/"missing")])[1]==2
