from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_invocation_common import *
SCHEMA='zero.engineering.runtime_adapter_invocation_intake.v1'
ID_KEY='invocation_intake_id'
PREFIX='rtai-'
STATUS_KEY='intake_status'
STATUSES={'invalid', 'not_accepted', 'accepted'}
FIELDS=set(['activation_handoff_id', 'activation_handoff_fingerprint', 'activation_result_id', 'adapter_id', 'adapter_version', 'execution_session_id', 'invocation_descriptor_id', 'authority_reference', 'authority_constraints', 'invocation_intake_request_id', 'invocation_intake_request_fingerprint', 'requested_invocation_scope', 'requested_operation', 'input_bindings', 'expected_output_contract', 'invocation_constraints', 'resource_constraints', 'timeout_constraints', 'environment_constraints', 'reason_codes', 'adapter_loaded', 'adapter_code_executed', 'adapter_invoked', 'runtime_invoked', 'authority_consumed', 'mutation_performed'])
def _build(status, reasons, **kw):
 body={'schema':SCHEMA,**{k:v for k,v in kw.items() if k not in {STATUS_KEY,'reason_codes'}},STATUS_KEY:status,'reason_codes':normalize_reasons(reasons)}
 return stable_artifact(body,ID_KEY,PREFIX)
def _validate(v:Any):
 r=validate_artifact(v,schema=SCHEMA,id_key=ID_KEY,prefix=PREFIX,fields=FIELDS,status_key=STATUS_KEY,statuses=STATUSES)
 extra=[]
 if isinstance(v,Mapping): extra.extend(validate_common_invocation(v))
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def validate_runtime_adapter_invocation_intake(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_invocation_intake(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)

REQ_SCHEMA='zero.engineering.runtime_adapter_invocation_intake_request.v1'; REQ_ID='invocation_intake_request_id'; REQ_PREFIX='rtair-'; REQ_FIELDS=set('activation_handoff_id activation_handoff_fingerprint activation_result_id activation_result_fingerprint activation_verification_id activation_verification_fingerprint controlled_activation_id token_consumption_id token_id activation_authorization_id adapter_id adapter_version execution_session_id invocation_descriptor_id activated_scope activated_scope requested_invocation_scope requested_operation input_bindings expected_output_contract invocation_constraints resource_constraints timeout_constraints environment_constraints authority_reference authority_constraints intake_context request_input_fingerprint'.split())
def build_runtime_adapter_invocation_intake_request(activation_handoff:Mapping[str,Any], requested_invocation_scope:Any, requested_operation:Any, input_bindings:Any, expected_output_contract:Any, invocation_constraints:Any, resource_constraints:Any, timeout_constraints:Any, environment_constraints:Any, intake_context:Any):
 h=activation_handoff if isinstance(activation_handoff,Mapping) else {}
 body={'schema':REQ_SCHEMA,'activation_handoff_id':h.get('activation_handoff_id'),'activation_handoff_fingerprint':h.get('fingerprint'),'activation_result_id':h.get('activation_result_id'),'activation_result_fingerprint':h.get('activation_result_fingerprint'),'activation_verification_id':h.get('activation_verification_id'),'activation_verification_fingerprint':h.get('activation_verification_fingerprint'),'controlled_activation_id':h.get('controlled_activation_id'),'token_consumption_id':h.get('token_consumption_id'),'token_id':h.get('token_id'),'activation_authorization_id':h.get('activation_authorization_id'),'adapter_id':h.get('adapter_id'),'adapter_version':h.get('adapter_version'),'execution_session_id':h.get('execution_session_id'),'invocation_descriptor_id':h.get('invocation_descriptor_id'),'activated_scope':h.get('activated_scope'),'requested_invocation_scope':requested_invocation_scope,'requested_operation':requested_operation,'input_bindings':input_bindings,'expected_output_contract':expected_output_contract,'invocation_constraints':invocation_constraints,'resource_constraints':resource_constraints,'timeout_constraints':timeout_constraints,'environment_constraints':environment_constraints,'authority_reference':h.get('authority_reference'),'authority_constraints':h.get('authority_constraints'),'intake_context':intake_context,'request_input_fingerprint':canonical_fingerprint({'scope':requested_invocation_scope,'operation':requested_operation,'input_bindings':input_bindings})}
 return stable_artifact(body,REQ_ID,REQ_PREFIX)
def validate_runtime_adapter_invocation_intake_request(v):
 r=validate_artifact(v,schema=REQ_SCHEMA,id_key=REQ_ID,prefix=REQ_PREFIX,fields=REQ_FIELDS)
 extra=validate_common_invocation(v) if isinstance(v,Mapping) else []
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def inspect_runtime_adapter_invocation_intake_request(v):
 r=validate_runtime_adapter_invocation_intake_request(v); return inspect_result(r.valid,r.errors)
def build_runtime_adapter_invocation_intake(request, activation_handoff):
 q=request if isinstance(request,Mapping) else {}; h=activation_handoff if isinstance(activation_handoff,Mapping) else {}
 ok=validate_runtime_adapter_invocation_intake_request(q).valid and h.get('eligible_for_invocation_governance') is True and h.get('activation_governance_completed') is True and h.get('token_consumed') is True and q.get('activation_handoff_id')==h.get('activation_handoff_id') and q.get('activation_handoff_fingerprint')==h.get('fingerprint')
 st='accepted' if ok else ('invalid' if not isinstance(request,Mapping) else 'not_accepted')
 return _build(st, ['intake_accepted'] if ok else ['intake_not_accepted'], invocation_intake_request_id=q.get('invocation_intake_request_id'), invocation_intake_request_fingerprint=q.get('fingerprint'), activation_handoff_id=q.get('activation_handoff_id'), activation_handoff_fingerprint=q.get('activation_handoff_fingerprint'), activation_result_id=q.get('activation_result_id'), adapter_id=q.get('adapter_id'), adapter_version=q.get('adapter_version'), execution_session_id=q.get('execution_session_id'), invocation_descriptor_id=q.get('invocation_descriptor_id'), activated_scope=q.get('activated_scope'), requested_invocation_scope=q.get('requested_invocation_scope'), requested_operation=q.get('requested_operation'), input_bindings=q.get('input_bindings'), expected_output_contract=q.get('expected_output_contract'), invocation_constraints=q.get('invocation_constraints'), resource_constraints=q.get('resource_constraints'), timeout_constraints=q.get('timeout_constraints'), environment_constraints=q.get('environment_constraints'), authority_reference=q.get('authority_reference'), authority_constraints=q.get('authority_constraints'), adapter_loaded=False, adapter_code_executed=False, adapter_invoked=False, runtime_invoked=False, authority_consumed=False, mutation_performed=False)

