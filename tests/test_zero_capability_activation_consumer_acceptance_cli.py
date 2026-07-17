import json,subprocess,sys
from cli.zero_capability_activation_consumer_acceptance import run
from tests.test_runtime_capability_runtime_activation_admission_handoff import admission_handoff
def test_cli(tmp_path):
 p=tmp_path/"i.json";o=tmp_path/"o.json";p.write_text(json.dumps(admission_handoff()),encoding="utf-8");args=["--handoff",str(p),"--accepted-at","2099-07-17T06:03:25Z","--consumer-id","capability-runtime-activation-consumer","--output",str(o)];r,c=run(args);assert c==0 and r["accepted"] and json.loads(o.read_text())==r
 c=subprocess.run([sys.executable,"-m","cli.zero_capability_activation_consumer_acceptance",*args[:-2]],capture_output=True,text=True);assert c.returncode==0 and json.loads(c.stdout)["accepted"]
def test_errors(tmp_path):
 assert run(["--handoff",str(tmp_path/"x"),"--consumer-id","x"])[1]==2;p=tmp_path/"bad";p.write_text("{");assert run(["--handoff",str(p),"--consumer-id","x"])[1]==2
