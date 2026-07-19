from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_invocation_common import *
SCHEMA='zero.engineering.runtime_adapter_invocation_admission.v1'
ID_KEY='invocation_admission_id'
PREFIX='rtad-'
STATUS_KEY='admission_status'
STATUSES={'not_admitted', 'invalid', 'admitted'}
FIELDS=set(['activation_handoff_id', 'activation_result_id', 'adapter_id', 'adapter_version', 'execution_session_id', 'invocation_descriptor_id', 'authority_reference', 'authority_constraints', 'reason_codes', 'adapter_loaded', 'adapter_code_executed', 'adapter_invoked', 'runtime_invoked', 'authority_consumed', 'mutation_performed', 'invocation_intake_id', 'invocation_intake_fingerprint', 'admitted_scope', 'operation', 'input_bindings', 'expected_output_contract', 'resource_constraints', 'timeout_constraints', 'environment_constraints'])
def _build(status, reasons, **kw):
 body={'schema':SCHEMA,**{k:v for k,v in kw.items() if k not in {STATUS_KEY,'reason_codes'}},STATUS_KEY:status,'reason_codes':normalize_reasons(reasons)}
 return stable_artifact(body,ID_KEY,PREFIX)
def _validate(v:Any):
 r=validate_artifact(v,schema=SCHEMA,id_key=ID_KEY,prefix=PREFIX,fields=FIELDS,status_key=STATUS_KEY,statuses=STATUSES)
 extra=[]
 if isinstance(v,Mapping): extra.extend(validate_common_invocation(v))
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def validate_runtime_adapter_invocation_admission(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_invocation_admission(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)

POLICY_SCHEMA='zero.engineering.runtime_adapter_invocation_admission_policy.v1'; POLICY_ID='invocation_admission_policy_id'; POLICY_PREFIX='rtadp-'; POLICY_FIELDS=set('requires_accepted_intake requires_passive_inputs requires_bounded_scope requires_no_real_execution invalid_input_fails_closed reason_codes'.split())
def build_default_runtime_adapter_invocation_admission_policy(): return stable_artifact({'schema':POLICY_SCHEMA,'requires_accepted_intake':True,'requires_passive_inputs':True,'requires_bounded_scope':True,'requires_no_real_execution':True,'invalid_input_fails_closed':True,'reason_codes':['default_invocation_admission_policy']},POLICY_ID,POLICY_PREFIX)
def validate_runtime_adapter_invocation_admission_policy(v): return validate_artifact(v,schema=POLICY_SCHEMA,id_key=POLICY_ID,prefix=POLICY_PREFIX,fields=POLICY_FIELDS)
def inspect_runtime_adapter_invocation_admission_policy(v):
 r=validate_runtime_adapter_invocation_admission_policy(v); return inspect_result(r.valid,r.errors)
def build_runtime_adapter_invocation_admission(intake, policy=None):
 i=intake if isinstance(intake,Mapping) else {}; p=policy or build_default_runtime_adapter_invocation_admission_policy(); ok=validate_runtime_adapter_invocation_intake(i).valid and i.get('intake_status')=='accepted' and validate_runtime_adapter_invocation_admission_policy(p).valid
 st='admitted' if ok else ('invalid' if not isinstance(intake,Mapping) else 'not_admitted')
 return _build(st,['admitted'] if ok else ['not_admitted'], invocation_intake_id=i.get('invocation_intake_id'), invocation_intake_fingerprint=i.get('fingerprint'), activation_handoff_id=i.get('activation_handoff_id'), activation_result_id=i.get('activation_result_id'), adapter_id=i.get('adapter_id'), adapter_version=i.get('adapter_version'), execution_session_id=i.get('execution_session_id'), invocation_descriptor_id=i.get('invocation_descriptor_id'), admitted_scope=i.get('requested_invocation_scope'), operation=i.get('requested_operation'), input_bindings=i.get('input_bindings'), expected_output_contract=i.get('expected_output_contract'), resource_constraints=i.get('resource_constraints'), timeout_constraints=i.get('timeout_constraints'), environment_constraints=i.get('environment_constraints'), authority_reference=i.get('authority_reference'), authority_constraints=i.get('authority_constraints'), adapter_loaded=False, adapter_code_executed=False, adapter_invoked=False, runtime_invoked=False, authority_consumed=False, mutation_performed=False)
from core.engineering.engineering_runtime_adapter_invocation_intake import validate_runtime_adapter_invocation_intake
