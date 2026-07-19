import json,subprocess,sys,tempfile
from pathlib import Path
from tests.runtime_adapter_activation_authorization_fixtures import chain_auth, chain, request
CLI=[sys.executable,'cli/zero_engineering_runtime_adapter_activation_authorization.py']
def run(args,data=None):
 p=None
 if data is not None:
  f=tempfile.NamedTemporaryFile('w',delete=False,encoding='utf-8'); json.dump(data,f); f.close(); p=f.name
 r=subprocess.run(CLI+args+(([p] if p else [])),text=True,capture_output=True)
 if p: Path(p).unlink()
 return r,json.loads(r.stdout)
def test_all_actions_and_determinism():
 req,pol,rev,auth,hand,clo=chain_auth(); _,elig_handoff,elig_closure = None, chain()[5], chain()[6]
 actions=[('policy',None),('review',{'request':req,'policy':pol}),('authorize',{'request':req,'policy':pol,'review':rev}),('handoff',{'authorization':auth}),('closure',{'request':req,'policy':pol,'review':rev,'authorization':auth,'handoff':hand}),('validate',{'kind':'closure','artifact':clo}),('inspect',{'kind':'closure','artifact':clo})]
 for a,d in actions:
  r,o=run([a],d); assert r.returncode==0; assert 'Traceback' not in r.stderr+r.stdout
 r1,o1=run(['policy']); r2,o2=run(['policy']); assert o1==o2
def test_request_action_malformed_and_unsupported():
 *_,elig_handoff,elig_closure=chain(); data={'handoff':elig_handoff,'eligibility_closure':elig_closure,'requested_authorized_scope':{'operations':['observe']},'authorization_constraints':{'passive':True,'deterministic':True,'executable':False},'resource_constraints':{'cpu':1},'timeout_constraints':{'seconds':1,'finite':True,'perpetual':False},'environment_constraints':{'network':'disabled'},'authorization_context':{'purpose':'authorization'}}
 r,o=run(['request'],data); assert r.returncode==0 and o['schema'].endswith('request.v1')
 r,o=run(['bogus']); assert r.returncode!=0 and 'Traceback' not in r.stdout+r.stderr
