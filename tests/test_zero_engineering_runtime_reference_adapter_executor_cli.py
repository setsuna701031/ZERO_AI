import json, subprocess, sys
from tests.runtime_reference_adapter_executor_fixtures import handoff_for
def test_cli_registry_and_pipeline_deterministic():
 r=subprocess.run([sys.executable,'cli/zero_engineering_runtime_reference_adapter_executor.py','registry'],input='{}',text=True,capture_output=True,check=True); assert 'adapter_fingerprint' in r.stdout and 'execute' not in r.stdout
 h,c=handoff_for(); payload=json.dumps({'handoff':h,'closure':c,'input_payload':{'a':1}})
 a=subprocess.run([sys.executable,'cli/zero_engineering_runtime_reference_adapter_executor.py','pipeline'],input=payload,text=True,capture_output=True,check=True).stdout
 b=subprocess.run([sys.executable,'cli/zero_engineering_runtime_reference_adapter_executor.py','pipeline'],input=payload,text=True,capture_output=True,check=True).stdout
 assert a==b and 'traceback' not in a.lower()
