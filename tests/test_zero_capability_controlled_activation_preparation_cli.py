import json,subprocess,sys
from cli.zero_capability_controlled_activation_preparation import run
from tests.test_runtime_capability_activation_consumer_acceptance import acceptance
def test_cli(tmp_path):
 p=tmp_path/"i.json";o=tmp_path/"o.json";p.write_text(json.dumps(acceptance()),encoding="utf-8");args=["--acceptance",str(p),"--prepared-at","2099-07-17T06:03:26Z","--output",str(o)];r,c=run(args);assert c==0 and r["prepared"] and json.loads(o.read_text())==r
 c=subprocess.run([sys.executable,"-m","cli.zero_capability_controlled_activation_preparation",*args[:-2]],capture_output=True,text=True);assert c.returncode==0 and json.loads(c.stdout)["prepared"]
