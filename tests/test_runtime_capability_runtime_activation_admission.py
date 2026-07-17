from core.runtime.runtime_capability_runtime_activation_admission import admit_capability_runtime_activation as build
from tests.test_runtime_capability_runtime_activation_preparation import preparation
def admission(value=None,at="2099-07-17T06:03:23Z",**kw):return build(preparation() if value is None else value,admitted_at=at,**kw)
def test_admission_ttl_safe():
 x=admission();assert x["admitted"] and x["admission_ttl_seconds"]==30 and not x["runtime_activated"];assert admission(admission_ttl_seconds=45)["admitted"] and admission(admission_ttl_seconds=60)["blocked"] and admission(admission_ttl_seconds=61)["blocked"]
def test_ttl_mismatch():assert "ttl_mismatch" in admission(admission_expires_at="2099-07-17T06:03:40Z",admission_ttl_seconds=10)["errors"]
