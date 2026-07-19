import json, subprocess, sys
from tests.engineering_mutation_preparation_fixtures import valid_payload

def run(action,p):
 r=subprocess.run([sys.executable,'cli/zero_engineering_mutation_preparation.py',action,'--json',json.dumps(p)],capture_output=True,text=True)
 assert 'Traceback' not in r.stdout+r.stderr
 return r,json.loads(r.stdout)
def test_cli_pipeline_success_and_deterministic():
 p=valid_payload(); r1,o1=run('pipeline',p); r2,o2=run('pipeline',p); assert r1.returncode==0 and o1==o2 and o1['closure']['status']=='closed'
def test_cli_missing_decision_canonical_error():
 p=valid_payload(); p.pop('decision'); r,o=run('pipeline',p); assert r.returncode==2 and o['error']['code']=='operator_decision_required'
def test_cli_canonical_rejection():
 r,o=run('unknown',{}); assert r.returncode==2 and o['error']['code']=='unknown_action'
