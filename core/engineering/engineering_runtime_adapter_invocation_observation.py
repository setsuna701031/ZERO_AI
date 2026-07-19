from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_invocation_common import *
SCHEMA='zero.engineering.runtime_adapter_invocation_observation.v1'; ID_KEY='invocation_observation_id'; PREFIX='rtobs-'; STATUS_KEY='observation_status'; STATUSES={'observed','not_observed','invalid'}
FIELDS=set('controlled_invocation_id controlled_invocation_fingerprint invocation_authorization_id invocation_preparation_id activation_handoff_id adapter_id adapter_version execution_session_id invocation_descriptor_id observed_scope operation governance_transition_observed adapter_loaded_observed adapter_code_execution_observed adapter_invocation_observed runtime_invocation_observed executor_invocation_observed scheduler_invocation_observed external_effect_observed authority_consumption_observed mutation_observed observation_status reason_codes'.split())
def build_runtime_adapter_invocation_observation(controlled_invocation):
 c=controlled_invocation if isinstance(controlled_invocation,Mapping) else {}; ok=c.get('invocation_status')=='invoked' and c.get('governance_transition_committed') is True
 st='observed' if ok else ('invalid' if not isinstance(controlled_invocation,Mapping) else 'not_observed')
 return stable_artifact({'schema':SCHEMA,'controlled_invocation_id':c.get('controlled_invocation_id'),'controlled_invocation_fingerprint':c.get('fingerprint'),'invocation_authorization_id':c.get('invocation_authorization_id'),'invocation_preparation_id':c.get('invocation_preparation_id'),'activation_handoff_id':c.get('activation_handoff_id'),'adapter_id':c.get('adapter_id'),'adapter_version':c.get('adapter_version'),'execution_session_id':c.get('execution_session_id'),'invocation_descriptor_id':c.get('invocation_descriptor_id'),'observed_scope':c.get('invoked_scope'),'operation':c.get('operation'),'governance_transition_observed':ok,'adapter_loaded_observed':False,'adapter_code_execution_observed':False,'adapter_invocation_observed':False,'runtime_invocation_observed':False,'executor_invocation_observed':False,'scheduler_invocation_observed':False,'external_effect_observed':False,'authority_consumption_observed':False,'mutation_observed':False,'observation_status':st,'reason_codes':normalize_reasons([st])},ID_KEY,PREFIX)

def _validate(v):
 r=validate_artifact(v,schema=SCHEMA,id_key=ID_KEY,prefix=PREFIX,fields=FIELDS,status_key=STATUS_KEY,statuses=STATUSES); extra=validate_common_invocation(v) if isinstance(v,Mapping) else []
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def validate_runtime_adapter_invocation_observation(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_invocation_observation(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
