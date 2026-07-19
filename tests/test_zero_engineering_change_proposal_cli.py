import json, subprocess, sys
from tests.engineering_change_proposal_fixtures import policy_payload, upstream

def run_cli(action,payload):
 r=subprocess.run([sys.executable,'cli/zero_engineering_change_proposal.py',action,'--json',json.dumps(payload)],cwd='.',text=True,capture_output=True)
 return r,json.loads(r.stdout)
def test_cli_canonical_success_error_and_deterministic_pipeline():
 payload={'intent':{'intent_category':'create_text_file','summary_code':'demo','requested_target_paths':['src/new.txt'],'requested_operation_classes':['create_text_file'],'expected_goal_identifiers':['g1'],'expected_validation_identifiers':['v1'],'maximum_affected_files':1,'maximum_proposed_content_bytes':100,'maximum_diff_entries':5,'authority_constraints':['governance_only'],'scope_constraints':['src']},'workspace_evidence':upstream('src/new.txt','missing',None),'scope_policy':policy_payload(),'targets':['src/new.txt'],'changes':[{'operation_type':'create_text_file','target_relative_path':'src/new.txt','content':'new\n','before_content':''}]}
 r1,o1=run_cli('pipeline',payload); r2,o2=run_cli('pipeline',payload)
 assert r1.returncode==0 and o1==o2 and o1['closure']['status']=='closed'
 assert r1.stdout==json.dumps(o1,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n'
 r3,o3=run_cli('unknown',{})
 assert r3.returncode==2 and o3['error']['code']=='unknown_action'
 r4,o4=run_cli('intent','not a mapping')
 assert r4.returncode==2 and o4['error']['code']=='invalid_request' and 'Traceback' not in r4.stdout and 'Traceback' not in r4.stderr
