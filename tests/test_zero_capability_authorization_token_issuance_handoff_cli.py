import json,subprocess,sys
from cli.zero_capability_authorization_token_issuance_handoff import run
from tests.test_runtime_capability_authorization_token_issuance_handoff_preparation import prepare_handoff
def test_cli(tmp_path):
 p=tmp_path/"p.json";o=tmp_path/"o.json";p.write_text(json.dumps(prepare_handoff()),encoding="utf-8");r,c=run(["--preparation",str(p),"--handed-off-at","2099-07-17T06:03:20Z","--recipient-id","runtime-activation-governance","--output",str(o)]);assert c==0 and r["handed_off"] and json.loads(o.read_text())==r
def test_errors_module(tmp_path):
 assert run(["--preparation",str(tmp_path/"x"),"--recipient-id","x"])[1]==2;p=tmp_path/"p.json";p.write_text(json.dumps(prepare_handoff()),encoding="utf-8");assert run(["--preparation",str(p),"--handed-off-at","naive","--recipient-id","x"])[1]==2
 c=subprocess.run([sys.executable,"-m","cli.zero_capability_authorization_token_issuance_handoff","--preparation",str(p),"--handed-off-at","2099-07-17T06:03:20Z","--recipient-id","runtime-activation-governance"],capture_output=True,text=True);assert c.returncode==0 and json.loads(c.stdout)["handed_off"]
