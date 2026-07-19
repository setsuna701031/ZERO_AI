from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from tests.engineering_workspace_mutation_executor_fixtures import handoff

def test_cli_validation_only_no_write(tmp_path):
    (tmp_path/"sentinel.txt").write_text("sentinel",encoding="utf-8")
    p=json.dumps({"handoff":handoff(tmp_path)})
    r=subprocess.run([sys.executable,"cli/zero_engineering_workspace_mutation_executor.py","pipeline","--workspace-root",str(tmp_path),"--json",p],capture_output=True,text=True,check=True)
    out=json.loads(r.stdout)
    assert out["executor_admission"]["status"]=="admitted"
    assert not (tmp_path/".zero").exists()

def test_cli_execute_requires_confirmation(tmp_path):
    (tmp_path/"sentinel.txt").write_text("sentinel",encoding="utf-8")
    p=json.dumps({"handoff":handoff(tmp_path)})
    r=subprocess.run([sys.executable,"cli/zero_engineering_workspace_mutation_executor.py","pipeline","--execute","--workspace-root",str(tmp_path),"--json",p],capture_output=True,text=True)
    assert r.returncode==2
    assert "Traceback" not in r.stdout+r.stderr

def test_cli_execute_success(tmp_path):
    (tmp_path/"sentinel.txt").write_text("sentinel",encoding="utf-8")
    p=json.dumps({"handoff":handoff(tmp_path),"execute_confirmed":True})
    r=subprocess.run([sys.executable,"cli/zero_engineering_workspace_mutation_executor.py","pipeline","--execute","--workspace-root",str(tmp_path),"--json",p],capture_output=True,text=True,check=True)
    assert json.loads(r.stdout)["result"]["status"]=="succeeded"
    assert (tmp_path/"out.txt").exists()
