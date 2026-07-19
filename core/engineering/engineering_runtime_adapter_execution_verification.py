from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint, normalize_reasons
SCHEMA='zero.engineering.runtime_adapter_execution_verification.v1'
def verify_execution_result(result:Mapping[str,Any], submission:Mapping[str,Any], preflight:Mapping[str,Any], controlled:Mapping[str,Any], registry:Any)->dict[str,Any]:
 r=[]
 if result.get('submission_id')!=submission.get('submission_id'): r.append('submission_linkage_mismatch')
 if result.get('preflight_id')!=preflight.get('preflight_id'): r.append('preflight_linkage_mismatch')
 if result.get('controlled_execution_id')!=controlled.get('controlled_execution_id'): r.append('controlled_execution_linkage_mismatch')
 if any(controlled.get(k) is not False for k in ('external_effects_performed','filesystem_mutation_performed','network_access_performed','subprocess_created','thread_created','runtime_kernel_invoked','scheduler_invoked','planner_invoked','worker_invoked')): r.append('external_effect_invariant_failed')
 expected={'completed':'succeeded','cancelled':'cancelled','rejected':'rejected','failed':'failed'}.get(controlled.get('controlled_execution_status'),'invalid')
 if result.get('result_status')!=expected: r.append('status_mapping_mismatch')
 if result.get('result_status')!='cancelled' and ('output' in result)==('failure' in result): r.append('output_failure_exclusivity_mismatch')
 desc=registry.descriptor(submission.get('adapter_id'),submission.get('adapter_version')) if registry else None
 if result.get('adapter_descriptor_fingerprint')!=(desc or {}).get('fingerprint'): r.append('registry_binding_mismatch')
 body={'schema':SCHEMA,'verification_status':'verified' if not r else 'not_verified','result_id':result.get('result_id'),'result_fingerprint':result.get('fingerprint'),'reason_codes':normalize_reasons(r)}
 body['fingerprint']=canonical_fingerprint(body); body['verification_id']='ver-'+body['fingerprint'][:24]; return body
