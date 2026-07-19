from tests.engineering_mutation_preparation_fixtures import chain, valid_payload
from cli.zero_engineering_mutation_preparation import pipeline

def test_success_chain_artifacts():
 c=chain(); assert c['approval_policy']['status']=='active'; assert c['approval_request']['status']=='requested'; assert c['approval_eligibility']['status']=='eligible'; assert c['operator_decision']['status']=='approved'; assert c['approved_scope']['status']=='sealed'; assert c['approval_verification']['status']=='verified'; assert c['preparation_policy']['status']=='active'; assert c['preparation_request']['status']=='requested'; assert c['preparation_admission']['status']=='admitted'; assert all(o['status']=='prepared' for o in c['prepared_operations']); assert c['mutation_package']['status']=='packaged'; assert c['package_validation']['status']=='valid'; assert c['token_eligibility']['status']=='eligible'; assert c['preparation_token']['status']=='issued'; assert c['readiness_verification']['status']=='ready'; assert c['mutation_handoff']['status']=='handed_off'; assert c['closure']['status']=='closed'
def test_rejected_or_mutation_flag_rejects():
 p=valid_payload('rejected'); c=pipeline(p); assert c['approved_scope']['status']=='empty'; assert c['closure']['status']!='closed'
def test_flags_false_and_evidence_bounded():
 c=chain(); assert c['mutation_handoff']['mutation_authorized'] is False and c['preparation_token']['token_consumed'] is False; s=str(c['evidence']); assert 'content\'' not in s and 'raw diff' not in s.lower()
