from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint
from core.engineering.engineering_runtime_reference_adapter_protocol import DESCRIPTOR_SCHEMA, EXECUTION_MODE, SUPPORTS_CANCELLATION, build_reference_adapter_descriptor
from core.engineering.engineering_runtime_reference_adapter_registry import ReferenceAdapterRegistry
class _Adapter:
 adapter_version='1.0'; descriptor_schema=DESCRIPTOR_SCHEMA; input_contracts={'input.contract':{'canonical_json':True}}; output_contracts={'output.contract':{'canonical_json':True}}; deterministic=True; side_effect_free=True; supports_cancellation=SUPPORTS_CANCELLATION; execution_mode=EXECUTION_MODE
 def __init__(self): self.adapter_fingerprint=build_reference_adapter_descriptor(self)['adapter_fingerprint']
class CanonicalEchoAdapter(_Adapter):
 adapter_id='canonical_echo'; supported_operations=('echo',)
 def execute(self, operation:str, payload:Any, context:Mapping[str,Any])->Any:
  if operation!='echo': raise ValueError('unsupported')
  return payload
class CanonicalSelectAdapter(_Adapter):
 adapter_id='canonical_select'; supported_operations=('select',)
 def execute(self, operation:str, payload:Any, context:Mapping[str,Any])->Any:
  if operation!='select' or not isinstance(payload,Mapping): raise ValueError('unsupported')
  fields=payload.get('fields'); source=payload.get('source')
  if not isinstance(fields,list) or not all(isinstance(f,str) and len(f)<=128 for f in fields) or not isinstance(source,Mapping): raise ValueError('invalid')
  return {f:source[f] for f in sorted(fields) if f in source}
class CanonicalCompareAdapter(_Adapter):
 adapter_id='canonical_compare'; supported_operations=('compare',)
 def execute(self, operation:str, payload:Any, context:Mapping[str,Any])->Any:
  if operation!='compare' or not isinstance(payload,Mapping): raise ValueError('unsupported')
  return {'equal':payload.get('left')==payload.get('right')}
class CanonicalHashAdapter(_Adapter):
 adapter_id='canonical_hash'; supported_operations=('hash',)
 def execute(self, operation:str, payload:Any, context:Mapping[str,Any])->Any:
  if operation!='hash': raise ValueError('unsupported')
  return {'sha256':canonical_fingerprint(payload)}
def default_reference_adapters(): return (CanonicalEchoAdapter(),CanonicalSelectAdapter(),CanonicalCompareAdapter(),CanonicalHashAdapter())
def default_reference_adapter_registry(): return ReferenceAdapterRegistry(default_reference_adapters())
