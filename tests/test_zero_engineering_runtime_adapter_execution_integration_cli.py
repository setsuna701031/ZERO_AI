import json, subprocess, sys
from tests.runtime_adapter_execution_integration_fixtures import *
CLI=[sys.executable,'cli/zero_engineering_runtime_adapter_execution_integration.py']
def run(action,payload):
 return subprocess.run(CLI+[action],input=json.dumps(payload),text=True,capture_output=True)
def test_cli_success_and_error_no_traceback():
 r=run('capability',{'adapter_id':'adapter.identity','adapter_version':'1.0','supported_operation_names':['operation.identity']})
 assert r.returncode==0 and json.loads(r.stdout)['schema']=='zero.engineering.runtime_adapter_execution_capability.v1'
 e=subprocess.run(CLI+['nope'],input='{}',text=True,capture_output=True)
 assert e.returncode==1 and 'Traceback' not in e.stderr+e.stdout and json.loads(e.stdout)['error']['reason_code']=='unsupported_action'
def test_cli_validate():
 p=pipeline(); r=run('validate',{'artifact':p['hand']}); assert r.returncode==0 and json.loads(r.stdout)['valid'] is True
