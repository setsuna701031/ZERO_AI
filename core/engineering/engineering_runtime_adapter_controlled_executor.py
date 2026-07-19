from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint
from core.engineering.engineering_runtime_reference_adapter_protocol import execution_context
from core.engineering.engineering_runtime_adapter_execution_failure import build_execution_failure, normalize_exception
from core.engineering.engineering_runtime_adapter_execution_output import build_execution_output
SCHEMA='zero.engineering.runtime_adapter_controlled_execution.v1'
FLAGS={'external_effects_performed':False,'filesystem_mutation_performed':False,'network_access_performed':False,'subprocess_created':False,'thread_created':False,'runtime_kernel_invoked':False,'scheduler_invoked':False,'planner_invoked':False,'worker_invoked':False}
def _artifact(sub,pre,status,started=False,invoked=False,completed=False,failure=None,output=None):
 body={'schema':SCHEMA,'submission_id':sub.get('submission_id'),'preflight_id':pre.get('preflight_id'),'controlled_execution_status':status,'invocation_started':started,'adapter_invoked':invoked,'invocation_completed':completed,**FLAGS}
 if failure: body['failure']=failure
 if output: body['output']=output
 body['fingerprint']=canonical_fingerprint(body); body['controlled_execution_id']='xce-'+body['fingerprint'][:24]; return body
def execute_controlled_reference_adapter(submission:Mapping[str,Any], preflight:Mapping[str,Any], cancellation:Mapping[str,Any], registry:Any)->dict[str,Any]:
 if cancellation.get('cancellation_state')=='requested': return _artifact(submission,preflight,'cancelled')
 if submission.get('submission_status')!='accepted' or preflight.get('preflight_status')!='admitted': return _artifact(submission,preflight,'rejected',failure=build_execution_failure(submission,'preflight_rejected','pre_invocation'))
 adapter=registry.lookup(submission.get('adapter_id'),submission.get('adapter_version'))
 if adapter is None: return _artifact(submission,preflight,'rejected',failure=build_execution_failure(submission,'unknown_adapter','pre_invocation'))
 op=submission.get('allowed_operation',{}).get('operation_id') if isinstance(submission.get('allowed_operation'),Mapping) else submission.get('allowed_operation')
 try:
  raw=adapter.execute(op, submission.get('canonical_input_payload'), execution_context({'submission_id':submission.get('submission_id'),'execution_session_id':submission.get('execution_session_id'),'adapter_id':submission.get('adapter_id'),'adapter_version':submission.get('adapter_version'),'operation':op,'input_contract':submission.get('input_contract_identifier'),'output_contract':submission.get('expected_output_contract'),'max_output_bytes':65536}))
 except Exception as exc:
  return _artifact(submission,preflight,'failed',True,True,False,failure=normalize_exception(exc))
 out=build_execution_output(submission,raw,submission.get('expected_output_contract'))
 if not out.get('output_valid'):
  return _artifact(submission,preflight,'failed',True,True,False,failure=build_execution_failure(submission,'invalid_output','output_capture'))
 return _artifact(submission,preflight,'completed',True,True,True,output=out)
