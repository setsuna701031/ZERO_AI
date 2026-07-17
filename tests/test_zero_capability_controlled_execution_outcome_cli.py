import json
from cli.zero_capability_controlled_execution_outcome import run
from tests.test_runtime_capability_bounded_execution_request import request
def test_cli(tmp_path):
    p=tmp_path/"i.json";p.write_text(json.dumps(request()),encoding="utf-8");r,c=run(["--input",str(p),"--observed-status","completed","--evidence-json",'["evidence:1"]']);assert c==0 and r["status"]=="completed"
