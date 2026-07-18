import json,subprocess,sys
from cli.zero_capability_strategy_runtime_integration_decision import run
from tests.test_runtime_capability_strategy_runtime_integration_decision import configuration
def test_cli_decide_validate_inspect_and_source_unchanged(tmp_path):
 p=tmp_path/"source.json";p.write_text(json.dumps(configuration()),encoding="utf-8");original=p.read_bytes();out,code=run(["decide",str(p)]);assert code==0
 a=tmp_path/"artifact.json";a.write_text(json.dumps(out),encoding="utf-8");assert run(["validate",str(a)])[1]==0 and run(["inspect",str(a)])[0]["status"]=="decided" and p.read_bytes()==original
def test_cli_errors_have_no_traceback(tmp_path):
 p=tmp_path/"bad.json";p.write_text("{",encoding="utf-8");out,code=run(["decide",str(p)]);assert code==2 and out["error"]=="input_error"
 done=subprocess.run([sys.executable,"-m","cli.zero_capability_strategy_runtime_integration_decision","decide",str(p)],capture_output=True,text=True);assert done.returncode and "Traceback" not in done.stderr
