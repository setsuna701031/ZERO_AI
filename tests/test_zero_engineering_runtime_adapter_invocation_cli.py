import json, subprocess, sys

def run_cli(action, payload):
 return subprocess.run([sys.executable,'cli/zero_engineering_runtime_adapter_invocation.py',action],input=json.dumps(payload),text=True,capture_output=True)
def test_cli_policy_deterministic():
 a=run_cli('admission-policy',{}); b=run_cli('admission-policy',{}); assert a.returncode==0 and a.stdout==b.stdout and not a.stderr
def test_cli_malformed_and_unsupported_no_traceback():
 p=subprocess.run([sys.executable,'cli/zero_engineering_runtime_adapter_invocation.py','admission-policy'],input='{',text=True,capture_output=True); assert p.returncode and 'Traceback' not in p.stdout+p.stderr
 q=run_cli('missing',{}); assert q.returncode and 'unsupported_action' in q.stdout and not q.stderr
