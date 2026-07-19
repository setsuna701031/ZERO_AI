from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint, normalize_reasons, scope_subset, authority_subset
from core.engineering.engineering_runtime_adapter_executor_handoff import validate_runtime_adapter_executor_handoff
from core.engineering.engineering_runtime_adapter_execution_output import validate_canonical_payload
SCHEMA='zero.engineering.runtime_adapter_execution_submission.v1'
def build_execution_submission(handoff:Mapping[str,Any], closure:Mapping[str,Any], input_payload:Any, input_contract_identifier='input.contract', *, adapter_id=None, adapter_version=None, operation=None, approved_scope=None, authority_constraints=None, expected_output_contract=None, max_input_bytes=65536)->dict[str,Any]:
 reasons=[]; hv=validate_runtime_adapter_executor_handoff(handoff)
 if not hv.valid: reasons+=list(hv.errors)
 if handoff.get('real_execution_authorized') is not False: reasons.append('upstream_real_execution_authorized_not_false')
 if closure.get('fingerprint')!=handoff.get('upstream_closure_fingerprint') and closure.get('execution_integration_closure_id')!=handoff.get('upstream_execution_integration_closure_id'): reasons.append('upstream_closure_mismatch')
 aid=adapter_id or handoff.get('adapter_id'); ver=adapter_version or handoff.get('adapter_version'); op=operation or handoff.get('allowed_operation'); scope=approved_scope or handoff.get('approved_scope'); auth=authority_constraints or handoff.get('authority_constraints'); out=expected_output_contract or handoff.get('expected_output_contract')
 if aid!=handoff.get('adapter_id'): reasons.append('adapter_substitution')
 if ver!=handoff.get('adapter_version'): reasons.append('version_substitution')
 if op!=handoff.get('allowed_operation'): reasons.append('operation_substitution')
 if not scope_subset(scope,handoff.get('approved_scope')): reasons.append('scope_expansion')
 if not authority_subset(auth,handoff.get('authority_constraints')): reasons.append('authority_expansion')
 if out!=handoff.get('expected_output_contract'): reasons.append('output_contract_drift')
 okp,perrs,bc=validate_canonical_payload(input_payload,max_bytes=max_input_bytes); reasons+=list(perrs)
 body={'schema':SCHEMA,'executor_handoff_id':handoff.get('executor_handoff_id'),'executor_handoff_fingerprint':handoff.get('fingerprint'),'execution_envelope_id':handoff.get('execution_envelope_id'),'execution_envelope_fingerprint':handoff.get('execution_envelope_fingerprint'),'adapter_id':aid,'adapter_version':ver,'execution_session_id':handoff.get('execution_session_id'),'approved_scope':scope,'allowed_operation':op,'expected_input_contract':input_contract_identifier,'expected_output_contract':out,'authority_constraints':auth,'resource_budget_reference':handoff.get('resource_budget_id'),'timeout_policy_reference':handoff.get('timeout_policy_id'),'isolation_policy_reference':handoff.get('isolation_policy_id'),'environment_admission_reference':handoff.get('environment_admission_id'),'readiness_verification_reference':handoff.get('readiness_verification_id'),'upstream_execution_integration_closure_id':closure.get('execution_integration_closure_id'),'upstream_execution_integration_closure_fingerprint':closure.get('fingerprint'),'canonical_input_payload':input_payload if okp else None,'input_contract_identifier':input_contract_identifier,'input_byte_count':bc,'submission_status':'accepted' if not reasons else 'rejected','reason_codes':normalize_reasons(reasons)}
 body['submission_fingerprint']=canonical_fingerprint(body); body['fingerprint']=body['submission_fingerprint']; body['submission_id']='sub-'+body['fingerprint'][:24]; return body
