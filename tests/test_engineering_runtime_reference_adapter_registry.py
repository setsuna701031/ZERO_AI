import pytest
from core.engineering.engineering_runtime_reference_adapters import CanonicalEchoAdapter, default_reference_adapter_registry
from core.engineering.engineering_runtime_reference_adapter_registry import ReferenceAdapterRegistry
def test_registry_snapshot_duplicate_lookup_unknown():
 r=default_reference_adapter_registry(); assert r.snapshot()==default_reference_adapter_registry().snapshot(); assert r.lookup('canonical_echo','1.0') is not None; assert r.lookup('missing','1.0') is None
 with pytest.raises(ValueError): ReferenceAdapterRegistry((CanonicalEchoAdapter(),CanonicalEchoAdapter()))
