import json,subprocess,sys
from cli.zero_capability_activation_verification_closure import run
from tests.test_runtime_capability_controlled_activation_outcome import outcome
def test_cli(tmp_path):
 p=tmp_path/"i.json";o=tmp_path/"o.json";p.write_text(json.dumps(outcome()),encoding="utf-8");args=["--outcome-record",str(p),"--verified-at","2099-07-17T06:03:28Z","--verifier-id","capability-runtime-activation-verifier","--output",str(o)];r,c=run(args);assert c==0 and r["verified"] and json.loads(o.read_text())==r
 c=subprocess.run([sys.executable,"-m","cli.zero_capability_activation_verification_closure",*args[:-2]],capture_output=True,text=True);assert c.returncode==0 and json.loads(c.stdout)["verified"]
