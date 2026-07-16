from copy import deepcopy

from core.runtime.runtime_capability_detector import RuntimeCapabilityDetector
from core.runtime.runtime_capability_validation import validate_capability_profile


def test_detected_profile_is_valid_and_tampering_is_rejected():
    profile = RuntimeCapabilityDetector([]).detect().to_dict()
    assert validate_capability_profile(profile).valid
    tampered = deepcopy(profile); tampered["cpu"]["logical_cores"] = -1
    result = validate_capability_profile(tampered)
    assert not result.valid
    assert "invalid_logical_cores" in result.errors
    assert "fingerprint_mismatch" in result.errors


def test_duplicate_tools_are_invalid():
    profile = RuntimeCapabilityDetector([]).detect().to_dict()
    profile["available_tools"] = [{"name": "git"}, {"name": "git"}]
    assert "duplicate_entries:available_tools" in validate_capability_profile(profile).errors


def test_non_json_profile_returns_validation_error_instead_of_raising():
    profile = RuntimeCapabilityDetector([]).detect().to_dict()
    profile["constraints"] = [{"bad": {1}}]
    assert "not_json_serializable" in validate_capability_profile(profile).errors
