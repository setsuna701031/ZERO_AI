import json
from cli.zero_capability_runtime_activation_preparation import run
from tests.test_runtime_capability_runtime_activation_eligibility import eligibility
def test_cli(tmp_path):
 p=tmp_path/"i.json";p.write_text(json.dumps(eligibility()),encoding="utf-8");r,c=run(["--eligibility",str(p),"--prepared-at","2099-07-17T06:03:22Z"]);assert c==0 and r["prepared"]
