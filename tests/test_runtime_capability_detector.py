from core.runtime.runtime_capability_detector import RuntimeCapabilityDetector
import socket


class BrokenAdapter:
    name, section = "safe_broken", "memory"
    def detect(self): raise RuntimeError("secret detail must not leak")


def test_adapter_failure_is_isolated_and_diagnostic_is_safe():
    profile = RuntimeCapabilityDetector([BrokenAdapter()]).detect().to_dict()
    assert profile["diagnostics"] == [{"adapter": "safe_broken", "error_type": "RuntimeError", "reason_code": "adapter_detection_failed"}]
    assert "secret detail" not in str(profile)


def test_repeated_detection_has_stable_identity_for_normalized_inputs():
    first = RuntimeCapabilityDetector([]).detect(detected_at="one").to_dict()
    second = RuntimeCapabilityDetector([]).detect(detected_at="two").to_dict()
    assert (first["profile_id"], first["fingerprint"]) == (second["profile_id"], second["fingerprint"])


def test_raw_hostname_is_not_exposed():
    profile = RuntimeCapabilityDetector([]).detect().to_dict()
    assert profile["host"]["hostname"].startswith("host-")
    assert profile["host"]["hostname"] != socket.gethostname()
