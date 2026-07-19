import json,subprocess,sys
from pathlib import Path
from tests.runtime_adapter_admission_fixtures import pipeline,upstream,AUTH
CLI=[sys.executable,'-m','cli.zero_engineering_runtime_adapter_admission']
def run(tmp_path,action,data=None,*extra):
 p=tmp_path/'in.json';
 if data is not None: p.write_text(json.dumps(data),encoding='utf-8')
 return subprocess.run(CLI+[action]+(([str(p)] if data is not None else []))+list(extra),text=True,capture_output=True)
def test_cli_strict_json_deterministic_and_invalid(tmp_path):
 h,s,a=upstream(); data={'handoff':h,'session':s,'admission':a,'requested_adapter_id':'adapter.one','requested_adapter_version':'1.0.0','requested_scope':{'files':['a']},'authority_reference':'opaque','authority_constraints':AUTH}
 x=run(tmp_path,'request',data); y=run(tmp_path,'request',data); assert x.returncode==0 and x.stdout==y.stdout and json.loads(x.stdout)['schema'].endswith('request.v1')
 bad=run(tmp_path,'request',{'bad':True}); assert bad.returncode!=0 and json.loads(bad.stdout)['error']=='input_error'
def test_cli_actions_validate_inspect(tmp_path):
 r,p,e,a,*_=pipeline(); c=run(tmp_path,'closure',{'request':r,'policy':p,'eligibility':e,'admission':a}); assert c.returncode==0
 v=run(tmp_path,'validate',{'artifact':a},'--kind','admission'); assert v.returncode==0 and json.loads(v.stdout)['valid']
 i=run(tmp_path,'inspect',{'artifact':e},'--kind','eligibility'); assert i.returncode==0 and json.loads(i.stdout)['valid']
