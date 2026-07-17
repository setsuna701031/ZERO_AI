import json
from cli.zero_capability_bounded_execution_request import run
from tests.test_runtime_capability_execution_authority import authority
def test_cli(tmp_path):
    p=tmp_path/"i.json";p.write_text(json.dumps(authority()),encoding="utf-8");r,c=run(["--input",str(p),"--operation-class","inspect","--target-json",'{"resource":"profile"}']);assert c==0 and r["status"]=="accepted"
