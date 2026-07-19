from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint
SCHEMA='zero.engineering.runtime_adapter_execution_result.v1'
def build_execution_result(submission:Mapping[str,Any], preflight:Mapping[str,Any], descriptor:Mapping[str,Any], controlled:Mapping[str,Any], cancellation:Mapping[str,Any])->dict[str,Any]:
 cs=controlled.get('controlled_execution_status'); status={'completed':'succeeded','cancelled':'cancelled','rejected':'rejected','failed':'failed'}.get(cs,'invalid')
 body={'schema':SCHEMA,'result_status':status,'submission_id':submission.get('submission_id'),'submission_fingerprint':submission.get('fingerprint'),'preflight_id':preflight.get('preflight_id'),'preflight_fingerprint':preflight.get('fingerprint'),'adapter_descriptor_fingerprint':descriptor.get('fingerprint') if descriptor else None,'controlled_execution_id':controlled.get('controlled_execution_id'),'controlled_execution_fingerprint':controlled.get('fingerprint'),'cancellation_id':cancellation.get('cancellation_id'),'execution_session_id':submission.get('execution_session_id'),'adapter_id':submission.get('adapter_id'),'adapter_version':submission.get('adapter_version'),'operation':submission.get('allowed_operation'),'input_contract':submission.get('input_contract_identifier'),'output_contract':submission.get('expected_output_contract'),'upstream_handoff_id':submission.get('executor_handoff_id'),'upstream_closure_id':submission.get('upstream_execution_integration_closure_id')}
 if 'output' in controlled: body['output']=controlled['output']
 if 'failure' in controlled: body['failure']=controlled['failure']
 body['fingerprint']=canonical_fingerprint(body); body['result_id']='res-'+body['fingerprint'][:24]; return body
