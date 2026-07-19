from core.engineering.engineering_mutation_preparation_common import canonical_json,fingerprint,prohibited_payload
from tests.engineering_mutation_preparation_fixtures import chain,valid_payload

def test_canonical_deterministic(): assert canonical_json({'b':1,'a':2})=='{"a":2,"b":1}' and fingerprint({'a':1})==fingerprint({'a':1})
def test_pipeline_closes_and_deterministic(): assert chain()==chain() and chain()['closure']['status']=='closed'
def test_missing_operator_decision_error():
 from cli.zero_engineering_mutation_preparation import pipeline
 p=valid_payload(); p.pop('decision'); assert pipeline(p)['error']['code']=='operator_decision_required'
def test_prohibited_payload_detection(): assert prohibited_payload({'password':'x'})
