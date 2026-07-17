import json
from cli.zero_capability_runtime_activation_eligibility import run
from tests.test_runtime_capability_authorization_token_issuance_handoff import handoff
def test_cli(tmp_path):
 p=tmp_path/"i.json";o=tmp_path/"o.json";p.write_text(json.dumps(handoff()),encoding="utf-8");r,c=run(["--handoff",str(p),"--evaluated-at","2099-07-17T06:03:21Z","--output",str(o)]);assert c==0 and r["eligible"] and json.loads(o.read_text())==r
