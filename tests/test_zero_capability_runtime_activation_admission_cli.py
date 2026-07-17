import json
from cli.zero_capability_runtime_activation_admission import run
from tests.test_runtime_capability_runtime_activation_preparation import preparation
def test_cli(tmp_path):
 p=tmp_path/"i.json";p.write_text(json.dumps(preparation()),encoding="utf-8");r,c=run(["--preparation",str(p),"--admitted-at","2099-07-17T06:03:23Z","--ttl-seconds","30"]);assert c==0 and r["admitted"]
