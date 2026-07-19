from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint
from core.engineering.engineering_runtime_reference_adapter_protocol import build_reference_adapter_descriptor, validate_reference_adapter_descriptor
REGISTRY_SCHEMA='zero.engineering.runtime_reference_adapter_registry_snapshot.v1'
class ReferenceAdapterRegistry:
 def __init__(self, adapters=()):
  self._adapters={}; self._descriptors={}
  for a in adapters: self.register(a)
 def register(self, adapter:Any):
  d=build_reference_adapter_descriptor(adapter); ok,errs=validate_reference_adapter_descriptor(d)
  if not ok: raise ValueError('invalid_descriptor')
  key=(d['adapter_id'],d['adapter_version'])
  if key in self._adapters: raise ValueError('duplicate_adapter_registration')
  self._adapters[key]=adapter; self._descriptors[key]=d
 def lookup(self, adapter_id:str, adapter_version:str): return self._adapters.get((adapter_id,adapter_version))
 def descriptor(self, adapter_id:str, adapter_version:str): return self._descriptors.get((adapter_id,adapter_version))
 def snapshot(self)->dict[str,Any]:
  desc=[self._descriptors[k] for k in sorted(self._descriptors)]
  body={'schema':REGISTRY_SCHEMA,'descriptors':desc}
  body['registry_fingerprint']=canonical_fingerprint(body); body['fingerprint']=body['registry_fingerprint']; return body
