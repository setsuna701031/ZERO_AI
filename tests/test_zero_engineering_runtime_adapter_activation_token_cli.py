import json,subprocess,sys
from pathlib import Path
from tests.runtime_adapter_activation_token_fixtures import chain_token, eligibility_request, CONSTRAINTS, AUTHORITY
CLI=[sys.executable,'cli/zero_engineering_runtime_adapter_activation_token.py']
def run(action,payload=None,tmp_path=None,kind=None):
    args=CLI+[action]
    if payload is not None:
        p=tmp_path/'in.json'; p.write_text(json.dumps(payload),encoding='utf-8'); args.append(str(p))
    if kind: args+=['--kind',kind]
    return subprocess.run(args,text=True,capture_output=True)
def test_cli_every_action_and_determinism(tmp_path):
    req,elig,ppol,prep,rr,rev,apol,auth,iss,ver,hof,clo=chain_token()
    payloads={'eligibility-request':{'handoff':__import__('tests.runtime_adapter_activation_token_fixtures',fromlist=['eligibility_request']).eligibility_request()[1],'closure':__import__('tests.runtime_adapter_activation_token_fixtures',fromlist=['eligibility_request']).eligibility_request()[2],'requested_token_scope':{'operations':['observe']},'requested_max_uses':1,'token_constraints':CONSTRAINTS,'authority_reference':'authority:activation-token','authority_constraints':AUTHORITY},'eligibility':{'request':req},'preparation-policy':None,'prepare':{'request':req,'eligibility':elig,'policy':ppol},'review-request':{'preparation':prep,'eligibility':elig},'review':{'request':rr,'preparation':prep,'eligibility':elig},'authorization-policy':None,'authorize':{'review_request':rr,'review':rev,'preparation':prep,'eligibility':elig,'policy':apol},'issue':{'authorization':auth,'review_request':rr},'verify':{'token':iss,'authorization':auth},'handoff':{'token':iss,'verification':ver},'closure':{'eligibility_request':req,'eligibility':elig,'preparation_policy':ppol,'preparation':prep,'review_request':rr,'review':rev,'authorization_policy':apol,'authorization':auth,'issuance':iss,'verification':ver,'handoff':hof}}
    for action,payload in payloads.items():
        r=run(action,payload,tmp_path); assert r.returncode==0, (action,r.stdout,r.stderr); out=json.loads(r.stdout); assert isinstance(out,dict); assert r.stderr==''; assert 'token_value' not in r.stdout and 'Traceback' not in r.stdout
    r1=run('issue',payloads['issue'],tmp_path); r2=run('issue',payloads['issue'],tmp_path); assert r1.stdout==r2.stdout
    v=run('validate',{'kind':'issue','artifact':iss},tmp_path); assert v.returncode==0 and json.loads(v.stdout)['valid'] is True
    i=run('inspect',{'kind':'closure','artifact':clo},tmp_path); assert i.returncode==0 and json.loads(i.stdout)['package_status']=='closed'
def test_cli_errors(tmp_path):
    p=tmp_path/'bad.json'; p.write_text('{bad',encoding='utf-8')
    r=subprocess.run(CLI+['validate',str(p),'--kind','issue'],text=True,capture_output=True); assert r.returncode!=0 and 'Traceback' not in r.stdout
    r=subprocess.run(CLI+['nope'],text=True,capture_output=True); assert r.returncode!=0 and 'Traceback' not in r.stdout
    iss=chain_token()[8]; bad=dict(iss); bad['current_uses']=1
    r=run('validate',{'kind':'issue','artifact':bad},tmp_path); assert r.returncode!=0
