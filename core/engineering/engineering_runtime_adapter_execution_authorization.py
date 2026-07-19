from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import *
SCHEMA='zero.engineering.runtime_adapter_execution_authorization.v1'; ID_KEY='execution_authorization_id'; PREFIX='eau-'; STATUS_KEY='authorization_status'; STATUSES={'denied', 'authorized', 'invalid'}
COMMON=set('adapter_id adapter_version execution_session_id invocation_descriptor_id activation_handoff_id activation_result_id invocation_handoff_id invocation_closure_id approved_scope allowed_operation expected_output_contract authority_constraints invocation_fingerprint upstream_closure_fingerprint real_execution_authorized executor_invoked runtime_invoked effects_performed mutation_performed'.split())

def _base_status(ok): return sorted(STATUSES)[-1] if False else None

def build_runtime_adapter_execution_authorization(*args, **kwargs):
 data=dict(kwargs)
 # positional dependency names are normalized by stage
 if SCHEMA.endswith('execution_request.v1'):
  names=['invocation_handoff','invocation_closure']
 else:
  names=['request','capability','binding_resolution','environment_admission','isolation_policy','resource_budget','timeout_policy','preparation','review','authorization','envelope','readiness','handoff','closure','invocation_handoff','invocation_closure','environment_profile','requirements']
 for n,v in zip(names,args): data[n]=v
 return _build(data)

def _pick(data,*names):
 for n in names:
  v=data.get(n)
  if isinstance(v,Mapping): return v
 return {}

def _ids_from(up):
 return {k:up.get(k) for k in COMMON if k in up}

def _build(data:Mapping[str,Any]):
 h=_pick(data,'invocation_handoff','request','preparation','review','authorization','envelope','readiness','handoff')
 base={'schema':SCHEMA, **_ids_from(h), 'real_execution_authorized':False,'executor_invoked':False,'runtime_invoked':False,'effects_performed':False,'mutation_performed':False}
 reasons=[]; ok=True
 if contains_prohibited(data): ok=False; reasons.append('prohibited_payload')
 if SCHEMA.endswith('execution_request.v1'):
  ih=_pick(data,'invocation_handoff'); cl=_pick(data,'invocation_closure')
  ok= bool(ih) and ih.get('eligible_for_concrete_adapter_execution') is True and ih.get('invocation_governance_completed') is True and passive_invariants(ih) and not contains_prohibited(ih)
  base.update({ 'invocation_handoff_id':ih.get('invocation_handoff_id'), 'invocation_closure_id':cl.get('invocation_closure_id'), 'adapter_id':ih.get('adapter_id'), 'adapter_version':ih.get('adapter_version'), 'execution_session_id':ih.get('execution_session_id'), 'invocation_descriptor_id':ih.get('invocation_descriptor_id'), 'activation_handoff_id':ih.get('activation_handoff_id'), 'activation_result_id':ih.get('activation_result_id'), 'approved_scope':ih.get('invocation_scope'), 'allowed_operation':ih.get('operation'), 'expected_output_contract':ih.get('expected_output_contract'), 'authority_constraints':ih.get('authority_constraints'), 'invocation_fingerprint':ih.get('fingerprint'), 'upstream_closure_fingerprint':cl.get('fingerprint')})
  base[STATUS_KEY]='accepted' if ok else 'invalid'
 elif SCHEMA.endswith('execution_capability.v1'):
  ops=dedupe(data.get('supported_operation_names',[])); outs=dedupe(data.get('supported_output_contract_identifiers',[])); iso=dedupe(data.get('supported_isolation_levels',[]));
  ok=bool(data.get('adapter_id')) and bool(data.get('adapter_version')) and bool(ops) and not contains_prohibited(data)
  base.update({'adapter_id':data.get('adapter_id'),'adapter_version':data.get('adapter_version'),'supported_operation_names':ops,'supported_input_contract_identifiers':dedupe(data.get('supported_input_contract_identifiers',[])),'supported_output_contract_identifiers':outs,'supported_execution_modes':dedupe(data.get('supported_execution_modes',['passive_preparation'])),'supported_cancellation_modes':dedupe(data.get('supported_cancellation_modes',['none_declared'])),'supported_timeout_bounds':data.get('supported_timeout_bounds',{}),'supported_resource_dimensions':dedupe(data.get('supported_resource_dimensions',[])),'supported_isolation_levels':iso,'capability_fingerprint':canonical_fingerprint(data)}); base[STATUS_KEY]='declared' if ok else 'invalid'
 elif SCHEMA.endswith('binding_resolution.v1'):
  r=_pick(data,'request'); c=_pick(data,'capability'); ok=r.get('adapter_id')==c.get('adapter_id') and r.get('adapter_version')==c.get('adapter_version') and r.get('allowed_operation',{}).get('operation_id') in c.get('supported_operation_names',[]) and not contains_prohibited(data); base.update(_ids_from(r)); base.update({'capability_id':c.get('capability_id'),'capability_fingerprint':c.get('fingerprint')}); base[STATUS_KEY]='resolved' if ok else 'invalid'
 elif SCHEMA.endswith('environment_admission.v1'):
  prof=data.get('environment_profile',data.get('profile',{})); req=data.get('requirements',{}); ok=isinstance(prof,Mapping) and prof.get('network_mode') in ('disabled','none','declared_only') and strict_int(prof.get('logical_cpu_count',1),1,1024) and strict_int(prof.get('memory_limit_bytes',1),1,10**15) and not contains_prohibited(prof); base.update({'normalized_environment_profile':prof,'environment_requirements':req}); base[STATUS_KEY]='admitted' if ok else 'not_admitted'
 elif SCHEMA.endswith('isolation_policy.v1'):
  level=data.get('isolation_level','none_declared'); ok=level in ('none_declared','in_process_restricted','isolated_process_required','sandbox_required','external_runtime_required'); base.update({'isolation_level':level,'isolation_implemented':False}); base[STATUS_KEY]='valid' if ok else 'invalid'
 elif SCHEMA.endswith('resource_budget.v1'):
  limits={'max_wall_time_ms':(1,86400000),'max_cpu_time_ms':(1,86400000),'max_memory_bytes':(1,10**12),'max_output_bytes':(0,10**9),'max_artifact_count':(0,100000),'max_retry_count':(0,100),'max_parallel_units':(1,1024)}; vals={k:data.get(k) for k in limits}; ok=all(strict_int(vals[k],*b) for k,b in limits.items()); base.update(vals); base[STATUS_KEY]='bounded' if ok else 'invalid'
 elif SCHEMA.endswith('timeout_policy.v1'):
  limits={'startup_timeout_ms':(1,3600000),'execution_timeout_ms':(1,86400000),'shutdown_timeout_ms':(1,3600000),'cancellation_grace_ms':(0,3600000)}; vals={k:data.get(k) for k in limits}; mode=data.get('cancellation_mode','none_declared'); ok=all(strict_int(vals[k],*b) for k,b in limits.items()) and mode in ('none_declared','cooperative','deferred'); base.update(vals); base['cancellation_mode']=mode; base[STATUS_KEY]='bounded' if ok else 'invalid'
 else:
  # chain stages
  deps=[v for v in data.values() if isinstance(v,Mapping)]
  ok=bool(deps) and all(passive_invariants(d) and not contains_prohibited(d) for d in deps)
  for d in deps: base.update(_ids_from(d))
  if 'review' in SCHEMA: base[STATUS_KEY]='approved' if ok else 'rejected'
  elif 'authorization' in SCHEMA: base.update({'integration_authorized':ok,'real_execution_authorized':False}); base[STATUS_KEY]='authorized' if ok else 'denied'
  elif 'envelope' in SCHEMA: base[STATUS_KEY]='sealed' if ok else 'invalid'
  elif 'readiness' in SCHEMA: base[STATUS_KEY]='ready' if ok else 'not_ready'
  elif 'executor_handoff' in SCHEMA: base.update({'execution_envelope_id':_pick(data,'envelope').get('execution_envelope_id'),'execution_envelope_fingerprint':_pick(data,'envelope').get('fingerprint')}); base[STATUS_KEY]='handed_off' if ok else 'invalid'
  elif 'closure' in SCHEMA: base[STATUS_KEY]='closed' if ok else 'not_closed'
  else: base[STATUS_KEY]='prepared' if ok else 'invalid'
 base['reason_codes']=normalize_reasons([] if ok else (reasons or ['validation_failed']))
 return stable_artifact(base,ID_KEY,PREFIX)

def validate_runtime_adapter_execution_authorization(v):
 r=validate_artifact(v,schema=SCHEMA,id_key=ID_KEY,prefix=PREFIX,fields={'reason_codes'},status_key=STATUS_KEY,statuses=STATUSES)
 return r

def inspect_runtime_adapter_execution_authorization(v):
 r=validate_runtime_adapter_execution_authorization(v); return inspect_result(r.valid,r.errors)
