import json,subprocess,sys
from cli.zero_capability_authorization_token_issuance import run
from tests.test_runtime_capability_authorization_token_issuance_preparation import prepare
def test_cli(tmp_path):
 p=tmp_path/"p.json";o=tmp_path/"o.json";p.write_text(json.dumps(prepare()),encoding="utf-8");r,c=run(["--preparation",str(p),"--issued-at","2099-07-17T06:03:10Z","--output",str(o)]);assert c==0 and r["issued"] and json.loads(o.read_text())==r
def test_errors_module(tmp_path):
 assert run(["--preparation",str(tmp_path/"x")])[1]==2;p=tmp_path/"p.json";p.write_text(json.dumps(prepare()),encoding="utf-8");assert run(["--preparation",str(p),"--issued-at","naive"])[1]==2
 c=subprocess.run([sys.executable,"-m","cli.zero_capability_authorization_token_issuance","--preparation",str(p),"--issued-at","2099-07-17T06:03:10Z"],capture_output=True,text=True);assert c.returncode==0 and json.loads(c.stdout)["issued"]
