import json, subprocess, sys
from pathlib import Path
from tests.runtime_adapter_activation_eligibility_fixtures import chain,request,handoff,review_closure
CLI=[sys.executable,'cli/zero_engineering_runtime_adapter_activation_eligibility.py']
def run(args,path=None):
 return subprocess.run(CLI+args+(([str(path)] if path else [])),text=True,capture_output=True)
def test_all_supported_actions_and_determinism(tmp_path):
 req,pol,prof,ev,elig,ho,clo=chain();
 for action,payload in [('policy',None),('request',{'handoff':handoff(),'review_closure':review_closure(),'requested_activation_scope':{'operations':['observe']},'activation_constraints':{'passive':True,'deterministic':True},'resource_constraints':{'cpu':1},'timeout_constraints':{'seconds':1,'finite':True,'perpetual':False},'environment_constraints':{'network':'disabled'},'request_context':{'purpose':'test'}}),('profile',{'request':req}),('evaluate',{'request':req,'policy':pol,'profile':prof}),('eligibility',{'request':req,'policy':pol,'profile':prof,'evaluation':ev}),('handoff',{'eligibility':elig}),('closure',{'request':req,'policy':pol,'profile':prof,'evaluation':ev,'eligibility':elig,'handoff':ho})]:
  p=None
  if payload is not None:
   p=tmp_path/f'{action}.json'; p.write_text(json.dumps(payload))
  a=run([action],p); b=run([action],p); assert a.returncode==0 and a.stdout==b.stdout and a.stderr==''
def test_validate_inspect_errors(tmp_path):
 req=chain()[0]; p=tmp_path/'v.json'; p.write_text(json.dumps({'kind':'request','artifact':req})); assert run(['validate'],p).returncode==0; assert run(['inspect'],p).returncode==0
 bad=tmp_path/'bad.json'; bad.write_text('{'); r=run(['policy'],bad); assert r.returncode!=0 and 'traceback' not in (r.stdout+r.stderr).lower()
 r=run(['nope']); assert r.returncode!=0 and 'traceback' not in (r.stdout+r.stderr).lower()
