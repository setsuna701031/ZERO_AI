from __future__ import annotations

from copy import deepcopy

from core.runtime.runtime_capability_detection import CapabilityDetectionOrchestrator
from core.runtime.runtime_capability_detection_validation import validate_capability_detection


def test_default_detection_validates():
    assert validate_capability_detection(CapabilityDetectionOrchestrator().detect(["cpu", "models"])).valid


def test_duplicate_domain_and_noncanonical_order_fail_validation():
    value = CapabilityDetectionOrchestrator().detect(["cpu", "models"])
    value["results"].append(deepcopy(value["results"][0])); value["completed_domains"].append("cpu")
    errors = validate_capability_detection(value).errors
    assert "duplicate_domain" in errors and "invalid_completed_domains" in errors


def test_fingerprint_mismatch_and_json_unsafe_values_fail():
    value = CapabilityDetectionOrchestrator().detect(["cpu"]); value["results"][0]["evidence"]["logical_cores"] = 999
    assert "fingerprint_mismatch" in validate_capability_detection(value).errors
    unsafe = CapabilityDetectionOrchestrator().detect(["cpu"]); unsafe["results"][0]["evidence"]["bad"] = {1, 2}
    errors = validate_capability_detection(unsafe).errors
    assert "sensitive_or_unsafe_value" in errors and "not_json_serializable" in errors


def test_sensitive_and_raw_exception_fields_fail():
    value = CapabilityDetectionOrchestrator().detect(["cpu"]); value["results"][0]["evidence"]["hostname"] = "secret-host"
    assert "sensitive_or_unsafe_value" in validate_capability_detection(value).errors

