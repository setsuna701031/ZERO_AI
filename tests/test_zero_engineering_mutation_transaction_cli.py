import json, subprocess, sys
from tests.engineering_mutation_transaction_fixtures import valid_payload
from core.engineering.engineering_mutation_transaction_common import canonical_json

def test_cli_pipeline_success():
    r=subprocess.run([sys.executable,'cli/zero_engineering_mutation_transaction.py','pipeline','--json',json.dumps(valid_payload())],capture_output=True,text=True,check=True)
    o=json.loads(r.stdout); assert o['closure']['status']=='closed'; assert r.stdout.strip()==canonical_json(o)

def test_cli_missing_authorization_decision_error():
    p=valid_payload(); p.pop('authorization_decision')
    r=subprocess.run([sys.executable,'cli/zero_engineering_mutation_transaction.py','pipeline','--json',json.dumps(p)],capture_output=True,text=True)
    assert 'Traceback' not in r.stdout+r.stderr; assert json.loads(r.stdout)['error']['code']=='authorization_decision_required'
