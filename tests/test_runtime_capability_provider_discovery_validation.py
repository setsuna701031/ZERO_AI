from core.runtime.runtime_capability_provider_discovery import discover_providers
from core.runtime.runtime_capability_provider_discovery_validation import validate_capability_provider_discovery
from tests.test_runtime_capability_provider_discovery import descriptor


def test_valid_snapshot_and_identity_tampering():
    value = discover_providers([descriptor("vendor.a")], domains=["cpu"])
    assert validate_capability_provider_discovery(value).valid
    value["fingerprint"] = "0" * 64
    assert "fingerprint_mismatch" in validate_capability_provider_discovery(value).errors


def test_consistency_and_unknown_fields_are_rejected_without_repair():
    value = discover_providers([descriptor("vendor.a")], domains=["cpu"]); value["extra"] = object(); value["unresolved_domains"] = ["cpu"]
    result = validate_capability_provider_discovery(value)
    assert not result.valid and "unexpected:extra" in result.errors and "not_json_serializable" in result.errors and "domain_consistency_mismatch" in result.errors
