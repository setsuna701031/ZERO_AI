from __future__ import annotations
from typing import Any
from core.engineering.engineering_task_artifact_adapter import EngineeringTaskArtifactAdapter, ArtifactAdapterError
from core.engineering.engineering_task_artifact_adapters import known_adapters

class ArtifactAdapterRegistryError(ValueError): pass

class ArtifactAdapterRegistry:
    def __init__(self, adapters=()):
        self._items=[]; self._by_id={}; self._by_owner={}
        for a in adapters: self.register(a)
    def register(self, adapter: EngineeringTaskArtifactAdapter):
        aid=adapter.descriptor.adapter_id; owner=(adapter.descriptor.phase, adapter.descriptor.supported_schema)
        if aid in self._by_id: raise ArtifactAdapterRegistryError('duplicate_adapter_id')
        if owner in self._by_owner: raise ArtifactAdapterRegistryError('duplicate_phase_schema_owner')
        self._by_id[aid]=adapter; self._by_owner[owner]=adapter; self._items.append(adapter); self._items.sort(key=lambda x:(x.descriptor.phase,x.descriptor.supported_schema,x.descriptor.adapter_id))
    def lookup(self, phase: str, schema: str):
        if not schema: raise ArtifactAdapterRegistryError('schema_missing')
        adapter=self._by_owner.get((phase,schema))
        if adapter is None: raise ArtifactAdapterRegistryError('unsupported_artifact_family')
        return adapter
    def get(self, adapter_id: str):
        try: return self._by_id[adapter_id]
        except KeyError as exc: raise ArtifactAdapterRegistryError('unknown_adapter') from exc
    def list(self): return tuple(self._items)
    def validate_artifact(self, phase: str, artifact: Any):
        if not isinstance(artifact, dict): raise ArtifactAdapterRegistryError('artifact_not_mapping')
        return self.lookup(phase, artifact.get('schema')).validate(artifact)
    def inventory(self): return [a.descriptor.as_dict() for a in self._items]

def default_registry(): return ArtifactAdapterRegistry(known_adapters())
