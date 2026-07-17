import json
from cli.zero_capability_execution_session_admission import run
from tests.test_runtime_capability_execution_session_admission import activation
def test_cli(tmp_path):
    p=tmp_path/"i.json";p.write_text(json.dumps(activation()),encoding="utf-8");r,c=run(["--input",str(p)]);assert c==0 and r["status"]=="admitted";assert run(["--input",str(tmp_path/"missing")])[1]==2
