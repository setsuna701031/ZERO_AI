from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
CLOSURE_SCHEMA='zero.engineering.task_orchestration_closure.v1'

def build_task_closure(state:Mapping[str,Any], status:str='succeeded', failure:Mapping[str,Any]|None=None)->dict[str,Any]:
    success=status=='succeeded'
    body={'schema':CLOSURE_SCHEMA,'task_id':state.get('task_id'),'final_lifecycle_state':'closed' if success else state.get('lifecycle_state'),'repository_identity':state.get('repository_identity'),'request_identity':state.get('request_identity'),'analysis_identity':state.get('analysis_identity'),'proposal_identity':state.get('proposal_identity'),'approval_identity':state.get('approval_identity'),'authorization_identity':state.get('authorization_identity'),'authorized_scope_identity':state.get('authorized_scope_identity'),'preparation_identity':state.get('preparation_identity'),'transaction_identity':state.get('transaction_identity'),'execution_result_identity':state.get('execution_result_identity'),'verification_identity':state.get('verification_identity'),'transaction_evidence_linkage':state.get('transaction_evidence_linkage'),'completed_phases':list(state.get('completed_phases',[])),'success':success,'failure_classification':None if success else (failure or state.get('failure') or {}).get('code','blocked'),'no_replay_statement':'execution_replay_prohibited','terminal':True}
    fp=fingerprint(body); body['closure_id']='engineering-task-closure-'+fp[:24]; body['closure_fingerprint']=fp; return body
