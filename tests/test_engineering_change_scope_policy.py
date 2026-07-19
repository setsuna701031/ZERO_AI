from tests.engineering_change_proposal_fixtures import *

def test_chain_success_and_determinism():
 c1=chain(); c2=chain(); assert c1['clo']['status']=='closed'; assert c1['prop']==c2['prop']

def test_rejections_and_boundaries():
 assert build_change_intent({'intent_category':'x','maximum_affected_files':0,'maximum_proposed_content_bytes':1,'maximum_diff_entries':1})['status']=='rejected'
 p=policy_payload(); p['maximum_affected_files']='5'; assert build_change_scope_policy(p)['status']=='rejected'
 pol=build_change_scope_policy(policy_payload())
 for bad in ['/x','../x','\\srv/share','C:/x','src/a:b','bad\x00path']:
  assert admit_change_target(bad,pol)['status']!='admitted'
 ev=bind_workspace_evidence(upstream()); assert ev['status']=='bound'
 u=upstream(); u['verification']['verification_status']='not_verified'; assert bind_workspace_evidence(u)['status']=='rejected'
 u=upstream(); u['closure']['closure_status']='not_closed'; assert bind_workspace_evidence(u)['status']=='rejected'
 assert build_proposed_content({'content':'password=secret'},pol)['status']=='rejected'
 assert build_proposed_content({'content':'x'*3000},pol)['status']=='rejected'
 assert build_change_operation({'operation_type':'create_text_file','target_relative_path':'src/new.txt'})==build_change_operation({'operation_type':'create_text_file','target_relative_path':'src/new.txt'})
 c=chain(); bad=dict(c['prop']); bad['mutation_performed']=True; assert validate_change_proposal(bad)['status']=='invalid'
 evd=c['evidence']; assert 'hello' not in str(evd); assert 'change_blocks' not in evd
 assert c['approval_handoff']['operator_approval_obtained'] is False and c['approval_handoff']['mutation_authorized'] is False
