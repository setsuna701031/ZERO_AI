from tests.engineering_mutation_transaction_fixtures import chain, valid_payload
from cli.zero_engineering_mutation_transaction import pipeline

def test_pipeline_success_and_false_invariants():
    c=chain(); assert c['closure']['status']=='closed'; assert c['executor_handoff']['transaction_execution_authorized'] is False; assert c['authorization_token']['token_consumed'] is False; assert c['transaction_plan']['transaction_started'] is False

def test_deterministic_pipeline():
    assert chain()==chain()

def test_rejected_or_missing_authorization_not_closed():
    p=valid_payload(); p['authorization_decision']={'authorizer_id':'human-a','authorizer_identity_class':'human_operator','decision':'rejected','decision_reason_code':'no','authorized_operation_ids':[],'decision_nonce':'n'}; c=pipeline(p); assert c['authorized_scope']['status']=='empty'; assert c['closure']['status']!='closed'
