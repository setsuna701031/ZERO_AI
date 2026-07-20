from __future__ import annotations
import json, subprocess, sys
from core.engineering.engineering_mutation_transaction_common import finish

CLI=[sys.executable,'cli/zero_engineering_task.py']

def run(*args):
    return subprocess.run(CLI+list(args), text=True, capture_output=True)

def test_cli_list_and_report():
    r=run('list-adapters')
    assert r.returncode==0 and json.loads(r.stdout)['adapters']
    r=run('compatibility-report')
    assert r.returncode==0 and json.loads(r.stdout)['schema'].endswith('compatibility.v1')

def test_cli_validate_and_reject_unknown():
    art=finish('mutx-handoff','mutation_executor_handoff','handoff_id',{'status':'handed_off'})
    r=run('validate-artifact','--json',json.dumps({'phase':'executor_handoff','artifact':art}))
    assert r.returncode==0
    r=run('validate-artifact','--json',json.dumps({'phase':'executor_handoff','artifact':{'schema':'x'}}))
    assert r.returncode==2

def test_cli_invalid_json_exit_code():
    r=run('list-adapters','--json','{')
    assert r.returncode==2
