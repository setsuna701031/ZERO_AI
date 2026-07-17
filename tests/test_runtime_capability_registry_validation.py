from __future__ import annotations

from copy import deepcopy

from core.runtime.runtime_capability_registry import build_default_capability_registry
from core.runtime.runtime_capability_registry_validation import validate_capability_registry


def test_default_snapshot_validates():
    assert validate_capability_registry(build_default_capability_registry().snapshot()).valid


def test_fingerprint_mismatch_and_sensitive_metadata_are_rejected():
    value = build_default_capability_registry().snapshot()
    value["entries"][0]["enabled"] = False
    assert "fingerprint_mismatch" in validate_capability_registry(value).errors
    sensitive = deepcopy(build_default_capability_registry().snapshot())
    sensitive["entries"][0]["metadata"]["token"] = "secret"
    assert "sensitive_field" in validate_capability_registry(sensitive).errors


def test_non_json_metadata_and_extra_fields_are_rejected():
    value = build_default_capability_registry().snapshot(); value["extra"] = object()
    result = validate_capability_registry(value)
    assert "unexpected:extra" in result.errors and "not_json_serializable" in result.errors

