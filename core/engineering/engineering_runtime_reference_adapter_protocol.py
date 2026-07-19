from __future__ import annotations
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint, canonical_json, canonical_nonempty, normalize_reasons
DESCRIPTOR_SCHEMA='zero.engineering.runtime_reference_adapter_descriptor.v1'
SUPPORTS_CANCELLATION='pre_start_only'; EXECUTION_MODE='synchronous_in_memory_reference'

def _canon(v:Any)->Any:
 if isinstance(v,Mapping): return {str(k):_canon(v[k]) for k in sorted(v)}
 if isinstance(v,(list,tuple)): return [_canon(x) for x in v]
 return v

def descriptor_fingerprint(body:Mapping[str,Any])->str:
 return canonical_fingerprint({k:v for k,v in body.items() if k not in {'adapter_fingerprint','fingerprint'}})

def build_reference_adapter_descriptor(adapter:Any)->dict[str,Any]:
 body={'schema':DESCRIPTOR_SCHEMA,'adapter_id':adapter.adapter_id,'adapter_version':adapter.adapter_version,'descriptor_schema':DESCRIPTOR_SCHEMA,'supported_operations':sorted(adapter.supported_operations),'input_contracts':_canon(adapter.input_contracts),'output_contracts':_canon(adapter.output_contracts),'deterministic':adapter.deterministic,'side_effect_free':adapter.side_effect_free,'supports_cancellation':adapter.supports_cancellation,'execution_mode':adapter.execution_mode}
 body['adapter_fingerprint']=descriptor_fingerprint(body); body['fingerprint']=body['adapter_fingerprint']
 return body

def validate_reference_adapter_descriptor(d:Any)->tuple[bool,tuple[str,...]]:
 e=[]
 if not isinstance(d,Mapping): return False,('descriptor_not_object',)
 for k in 'schema adapter_id adapter_version descriptor_schema supported_operations input_contracts output_contracts deterministic side_effect_free supports_cancellation execution_mode adapter_fingerprint fingerprint'.split():
  if k not in d: e.append('missing:'+k)
 if d.get('schema')!=DESCRIPTOR_SCHEMA or d.get('descriptor_schema')!=DESCRIPTOR_SCHEMA: e.append('invalid_schema')
 if not canonical_nonempty(d.get('adapter_id')): e.append('invalid_adapter_id')
 if not canonical_nonempty(d.get('adapter_version')): e.append('invalid_adapter_version')
 if d.get('deterministic') is not True: e.append('non_deterministic')
 if d.get('side_effect_free') is not True: e.append('side_effect_free_false')
 if d.get('supports_cancellation')!=SUPPORTS_CANCELLATION: e.append('unsupported_cancellation')
 if d.get('execution_mode')!=EXECUTION_MODE: e.append('unsupported_execution_mode')
 if d.get('adapter_fingerprint')!=descriptor_fingerprint(d) or d.get('fingerprint')!=d.get('adapter_fingerprint'): e.append('descriptor_fingerprint_mismatch')
 return not e, tuple(normalize_reasons(e))

def execution_context(metadata:Mapping[str,Any])->Mapping[str,Any]:
 allowed={k:metadata.get(k) for k in sorted(metadata) if k in {'submission_id','execution_session_id','adapter_id','adapter_version','operation','input_contract','output_contract','max_output_bytes'}}
 return MappingProxyType(allowed)
@runtime_checkable
class ReferenceAdapterProtocol(Protocol):
 adapter_id:str; adapter_version:str; descriptor_schema:str; supported_operations:tuple[str,...]; input_contracts:Mapping[str,Any]; output_contracts:Mapping[str,Any]; deterministic:bool; side_effect_free:bool; supports_cancellation:str; execution_mode:str; adapter_fingerprint:str
 def execute(self, operation:str, payload:Any, context:Mapping[str,Any])->Any: ...
