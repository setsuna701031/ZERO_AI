import json,subprocess,sys
from cli.zero_capability_authorization_token_issuance_handoff_preparation import run
from tests.test_runtime_capability_authorization_token_issuance import issue
def test_cli(tmp_path):
 p=tmp_path/"i.json";o=tmp_path/"o.json";p.write_text(json.dumps(issue()),encoding="utf-8");r,c=run(["--issuance",str(p),"--prepared-at","2099-07-17T06:03:15Z","--output",str(o)]);assert c==0 and r["prepared"] and json.loads(o.read_text())==r
def test_errors_module(tmp_path):
 assert run(["--issuance",str(tmp_path/"x")])[1]==2;p=tmp_path/"i.json";p.write_text(json.dumps(issue()),encoding="utf-8");assert run(["--issuance",str(p),"--prepared-at","naive"])[1]==2
 c=subprocess.run([sys.executable,"-m","cli.zero_capability_authorization_token_issuance_handoff_preparation","--issuance",str(p),"--prepared-at","2099-07-17T06:03:15Z"],capture_output=True,text=True);assert c.returncode==0 and json.loads(c.stdout)["prepared"]
