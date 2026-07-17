import json
from cli.zero_capability_execution_authority import run
from tests.test_runtime_capability_execution_session_admission import admission
def test_cli(tmp_path):
    p=tmp_path/"i.json";p.write_text(json.dumps(admission()),encoding="utf-8");r,c=run(["--input",str(p),"--scope-json",'{"resource":"profile"}']);assert c==0 and r["status"]=="authorized"
