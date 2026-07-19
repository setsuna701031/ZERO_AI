from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_invocation_common import *
SCHEMA='zero.engineering.runtime_adapter_invocation_evidence.v1'; ID_KEY='invocation_evidence_id'; PREFIX='rtev-'; STATUS_KEY='evidence_status'; STATUSES={'evidenced','not_evidenced','invalid'}
FIELDS=set('invocation_observation_id invocation_observation_fingerprint controlled_invocation_id controlled_invocation_fingerprint invocation_authorization_id adapter_id adapter_version execution_session_id invocation_descriptor_id evidenced_scope operation evidence_entries governance_transition_evidenced non_execution_invariants_evidenced authority_invariants_evidenced mutation_prohibition_evidenced evidence_status reason_codes'.split())
def build_runtime_adapter_invocation_evidence(observation, controlled_invocation):
 o=observation if isinstance(observation,Mapping) else {}; c=controlled_invocation if isinstance(controlled_invocation,Mapping) else {}; ok=o.get('observation_status')=='observed' and c.get('invocation_status')=='invoked'
 st='evidenced' if ok else ('invalid' if not isinstance(observation,Mapping) else 'not_evidenced')
 return stable_artifact({'schema':SCHEMA,'invocation_observation_id':o.get('invocation_observation_id'),'invocation_observation_fingerprint':o.get('fingerprint'),'controlled_invocation_id':c.get('controlled_invocation_id'),'controlled_invocation_fingerprint':c.get('fingerprint'),'invocation_authorization_id':c.get('invocation_authorization_id'),'adapter_id':c.get('adapter_id'),'adapter_version':c.get('adapter_version'),'execution_session_id':c.get('execution_session_id'),'invocation_descriptor_id':c.get('invocation_descriptor_id'),'evidenced_scope':c.get('invoked_scope'),'operation':c.get('operation'),'evidence_entries':normalize_reasons(['governance_transition_committed','non_execution_invariants_hold','authority_not_consumed','mutation_prohibited'] if ok else ['evidence_not_complete']),'governance_transition_evidenced':ok,'non_execution_invariants_evidenced':ok,'authority_invariants_evidenced':ok,'mutation_prohibition_evidenced':ok,'evidence_status':st,'reason_codes':normalize_reasons([st])},ID_KEY,PREFIX)

def _validate(v):
 r=validate_artifact(v,schema=SCHEMA,id_key=ID_KEY,prefix=PREFIX,fields=FIELDS,status_key=STATUS_KEY,statuses=STATUSES); extra=validate_common_invocation(v) if isinstance(v,Mapping) else []
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def validate_runtime_adapter_invocation_evidence(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_invocation_evidence(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
