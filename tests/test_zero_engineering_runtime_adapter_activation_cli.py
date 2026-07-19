import json, subprocess, sys
from pathlib import Path
from tests.runtime_adapter_activation_fixtures import pipeline
def run_cli(tmp_path, action, data, *extra):
 f=tmp_path/'in.json'; f.write_text(json.dumps(data), encoding='utf-8'); return subprocess.run([sys.executable,'cli/zero_engineering_runtime_adapter_activation.py',action,str(f),*extra],text=True,capture_output=True)
def test_cli_actions(tmp_path):
 p=pipeline();
 for action, data in [('admission-policy',{}),('preparation-policy',{}),('admit',{'request':p['ar'],'policy':p['ap'],'token_handoff':p['h']}),('prepare',{'admission':p['ad'],'policy':p['pp']}),('activate',{'preparation':p['pr'],'admission':p['ad']}),('consume-token',{'controlled_activation':p['ca']}),('result',{'controlled_activation':p['ca'],'token_consumption':p['tc']}),('verify',{'admission':p['ad'],'preparation':p['pr'],'controlled_activation':p['ca'],'token_consumption':p['tc'],'activation_result':p['rs']}),('handoff',{'activation_result':p['rs'],'activation_verification':p['vf'],'token_consumption':p['tc'],'controlled_activation':p['ca']}),('closure',{'admission_request':p['ar'],'admission_policy':p['ap'],'admission':p['ad'],'preparation_policy':p['pp'],'preparation':p['pr'],'controlled_activation':p['ca'],'token_consumption':p['tc'],'activation_result':p['rs'],'activation_verification':p['vf'],'activation_handoff':p['ho']})]:
  r=run_cli(tmp_path,action,data); assert r.returncode==0, (action,r.stdout,r.stderr); assert r.stderr==''; json.loads(r.stdout); assert 'Traceback' not in r.stdout
 r=run_cli(tmp_path,'validate',{'kind':'closure','artifact':p['cl']}); assert r.returncode==0
 r=run_cli(tmp_path,'inspect',{'kind':'closure','artifact':p['cl']}); assert r.returncode==0
 f=tmp_path/'bad.json'; f.write_text('{bad',encoding='utf-8'); r=subprocess.run([sys.executable,'cli/zero_engineering_runtime_adapter_activation.py','closure',str(f)],text=True,capture_output=True); assert r.returncode!=0 and 'Traceback' not in r.stdout+r.stderr
 r=run_cli(tmp_path,'bogus',{}); assert r.returncode!=0
