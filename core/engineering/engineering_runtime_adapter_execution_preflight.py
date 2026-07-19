from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint, normalize_reasons
from core.engineering.engineering_runtime_reference_adapter_protocol import validate_reference_adapter_descriptor, EXECUTION_MODE
SCHEMA='zero.engineering.runtime_adapter_execution_preflight.v1'
def build_execution_preflight(submission:Mapping[str,Any], registry:Any, cancellation:Mapping[str,Any]|None=None)->dict[str,Any]:
 r=[]; desc=registry.descriptor(submission.get('adapter_id'),submission.get('adapter_version')) if registry else None
 if submission.get('submission_status')!='accepted': r.append('submission_not_accepted')
 if not desc: r.append('unknown_adapter')
 else:
  ok,errs=validate_reference_adapter_descriptor(desc); r+=list(errs)
  op=submission.get('allowed_operation',{}).get('operation_id') if isinstance(submission.get('allowed_operation'),Mapping) else submission.get('allowed_operation')
  if op not in desc.get('supported_operations',[]): r.append('unsupported_operation')
  if submission.get('input_contract_identifier') not in desc.get('input_contracts',{}): r.append('unsupported_input_contract')
  cid=submission.get('expected_output_contract',{}).get('contract_id') if isinstance(submission.get('expected_output_contract'),Mapping) else submission.get('expected_output_contract')
  if cid not in desc.get('output_contracts',{}): r.append('unsupported_output_contract')
  if desc.get('execution_mode')!=EXECUTION_MODE: r.append('unsupported_execution_mode')
 if cancellation and cancellation.get('cancellation_state')=='requested': r.append('cancellation_requested')
 body={'schema':SCHEMA,'submission_id':submission.get('submission_id'),'submission_fingerprint':submission.get('fingerprint'),'adapter_id':submission.get('adapter_id'),'adapter_version':submission.get('adapter_version'),'adapter_descriptor_fingerprint':desc.get('fingerprint') if desc else None,'reference_execution_admitted':not r,'general_real_execution_authorized':False,'preflight_status':'admitted' if not r else 'rejected','reason_codes':normalize_reasons(r)}
 body['fingerprint']=canonical_fingerprint(body); body['preflight_id']='pre-'+body['fingerprint'][:24]; return body
