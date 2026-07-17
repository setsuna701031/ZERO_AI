import json,subprocess,sys
from cli.zero_capability_controlled_activation_outcome import run
from tests.test_runtime_capability_controlled_activation_preparation import preparation
def test_cli(tmp_path):
 p=tmp_path/"i.json";o=tmp_path/"o.json";p.write_text(json.dumps(preparation()),encoding="utf-8");args=["--preparation",str(p),"--outcome","activated","--observed-at","2099-07-17T06:03:27Z","--consumer-id","capability-runtime-activation-consumer","--evidence-code","consumer_reported_activation_success","--output",str(o)];r,c=run(args);assert c==0 and r["activated"] and json.loads(o.read_text())==r
 c=subprocess.run([sys.executable,"-m","cli.zero_capability_controlled_activation_outcome",*args[:-2]],capture_output=True,text=True);assert c.returncode==0 and json.loads(c.stdout)["activated"]
def test_errors(tmp_path):assert run(["--preparation",str(tmp_path/"x"),"--outcome","activated","--consumer-id","x","--evidence-code","ok"])[1]==2
