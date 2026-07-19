import json,subprocess,sys
from pathlib import Path
from tests.runtime_adapter_preparation_review_fixtures import pipeline3
from core.engineering.engineering_runtime_adapter_preparation_review_common import canonical_json
CLI=[sys.executable,'-m','cli.zero_engineering_runtime_adapter_preparation_review']
def run(args): return subprocess.run(CLI+args,text=True,capture_output=True)
def test_cli_actions(tmp_path):
 rr,pol,elig,findings,review,handoff,closure,prep,clo,desc=pipeline3();
 payloads={'request':{'preparation':prep,'closure':clo,'descriptor':desc,'review_context':{}},'eligibility':{'request':rr,'policy':pol},'findings':{'request':rr,'policy':pol,'eligibility':elig},'review':{'request':rr,'policy':pol,'eligibility':elig,'findings':findings},'handoff':{'review':review,'request':rr},'closure':{'request':rr,'policy':pol,'eligibility':elig,'findings':findings,'review':review,'handoff':handoff}}
 p=run(['policy']); assert p.returncode==0 and json.loads(p.stdout)['schema'].endswith('policy.v1')
 for action,data in payloads.items():
  f=tmp_path/(action+'.json'); f.write_text(json.dumps(data),encoding='utf-8'); r=run([action,str(f)]); assert r.returncode==0, r.stdout+r.stderr; assert json.loads(r.stdout)['schema'].endswith(action+'.v1')
 vf=tmp_path/'v.json'; vf.write_text(json.dumps({'kind':'review','artifact':review}),encoding='utf-8'); assert run(['validate',str(vf)]).returncode==0; assert run(['inspect',str(vf)]).returncode==0
 assert run(['bad']).returncode!=0
 bad=tmp_path/'bad.json'; bad.write_text('{',encoding='utf-8'); r=run(['validate',str(bad),'--kind','review']); assert r.returncode!=0 and 'Traceback' not in r.stdout+r.stderr
 r1=run(['policy']); r2=run(['policy']); assert r1.stdout==r2.stdout
