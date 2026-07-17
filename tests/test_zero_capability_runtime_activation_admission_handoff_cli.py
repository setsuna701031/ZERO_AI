import json
from cli.zero_capability_runtime_activation_admission_handoff import run
from tests.test_runtime_capability_runtime_activation_admission import admission
def test_cli(tmp_path):
 p=tmp_path/"i.json";p.write_text(json.dumps(admission()),encoding="utf-8");r,c=run(["--admission",str(p),"--handed-off-at","2099-07-17T06:03:24Z"]);assert c==0 and r["handed_off"]
