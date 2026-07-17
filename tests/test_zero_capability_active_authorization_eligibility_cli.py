import json,subprocess,sys
from cli.zero_capability_active_authorization_eligibility import run
from tests.test_runtime_capability_active_authorization_eligibility import decision,NOW

def write(tmp_path,status):
    path=tmp_path/(status+".json");path.write_text(json.dumps(decision(status)),encoding="utf-8");return path
def test_cli_statuses_and_output(tmp_path):
    for source,target in (("approved","eligible"),("denied","ineligible"),("blocked","blocked"),("invalid","invalid")):
        path=write(tmp_path,source);output=tmp_path/(source+"-out.json")
        value,code=run(["--decision",str(path),"--evaluated-at",NOW,"--output",str(output)])
        assert code==0 and value["status"]==target and json.loads(output.read_text(encoding="utf-8"))==value
        assert not any(value[k] for k in ("active_authorization_created","token_issued","runtime_activated","execution_authority_granted"))
def test_cli_bad_file_json_and_timestamp(tmp_path):
    assert run(["--decision",str(tmp_path/"missing")])[1]!=0
    bad=tmp_path/"bad";bad.write_text("bad",encoding="utf-8");assert run(["--decision",str(bad)])[1]!=0
    assert run(["--decision",str(write(tmp_path,"approved")),"--evaluated-at","2026-01-01T00:00:00"])[1]!=0
def test_python_m_entrypoint(tmp_path):
    result=subprocess.run([sys.executable,"-m","cli.zero_capability_active_authorization_eligibility","--decision",str(write(tmp_path,"approved")),"--evaluated-at",NOW],capture_output=True,text=True)
    assert result.returncode==0 and json.loads(result.stdout)["eligible"] and "Traceback" not in result.stderr
