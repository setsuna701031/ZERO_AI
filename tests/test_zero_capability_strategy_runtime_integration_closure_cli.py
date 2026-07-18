import json,subprocess,sys
from cli.zero_capability_strategy_runtime_integration_closure import run
from tests.test_runtime_capability_strategy_runtime_integration_closure import verification
def test_cli_close_validate_inspect_and_source_unchanged(tmp_path):
 p=tmp_path/"v.json";p.write_text(json.dumps(verification()),encoding="utf-8");before=p.read_bytes();out,code=run(["close",str(p)]);assert code==0
 a=tmp_path/"c.json";a.write_text(json.dumps(out),encoding="utf-8");assert run(["validate",str(a)])[1]==0 and run(["inspect",str(a)])[0]["verification_closed"] is True and p.read_bytes()==before
def test_cli_failure_is_nonzero_without_traceback(tmp_path):
 p=tmp_path/"bad";p.write_text("{",encoding="utf-8");done=subprocess.run([sys.executable,"-m","cli.zero_capability_strategy_runtime_integration_closure","close",str(p)],capture_output=True,text=True);assert done.returncode and "Traceback" not in done.stderr and json.loads(done.stdout)["error"]=="input_error"
