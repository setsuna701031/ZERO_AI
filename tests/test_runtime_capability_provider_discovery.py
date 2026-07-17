from __future__ import annotations

import json

import pytest

from core.runtime.runtime_capability_detection import CapabilityDetectionOrchestrator, DetectionContext
from core.runtime.runtime_capability_provider_discovery import DiscoveryError, ProcessLocalProviderBindings, discovery_to_detection_plan, discover_providers, normalize_descriptor


def descriptor(provider_id: str, detector_id: str = "cpu_detector", *, domain: str = "cpu", priority: int = 100, **changes):
    value = {"provider_id": provider_id, "detector_id": detector_id, "domain": domain, "provider_version": "1.0", "priority": priority, "supported_platform_families": ["any"], "supported_architectures": ["any"], "supported_python_versions": ["any"], "implementation_kind": "process_local", "source_kind": "explicit", "enabled": True, "default": False, "metadata": {"safe": True}}
    value.update(changes); return value


class FakeProvider:
    supported_platforms = ("any",); priority = 100; detector_id = "cpu_detector"; domain = "cpu"
    def __init__(self, calls): self.calls = calls
    def detect(self, context: DetectionContext):
        self.calls.append("detect")
        return {"detector_id": self.detector_id, "domain": self.domain, "status": "available", "evidence": {"ok": True}, "error_code": None, "provider": {"schema": "zero.runtime.capability_detector_provider.v1", "provider_version": 1, "detector_id": self.detector_id, "domain": self.domain, "priority": 100, "supported_platforms": ["any"]}}


def test_descriptor_and_discovery_identity_are_deterministic_and_order_independent():
    a, b = descriptor("vendor.a", priority=100), descriptor("vendor.b", "cpu_b", priority=200)
    assert normalize_descriptor(a)["fingerprint"] == normalize_descriptor(dict(reversed(list(a.items()))))["fingerprint"]
    left = discover_providers([a, b], domains=["cpu"], context={"platform_family": "linux", "architecture": "x86_64", "python_version": "3.12"})
    right = discover_providers([b, a], domains=["cpu"], context={"platform_family": "linux", "architecture": "x86_64", "python_version": "3.12"})
    assert left == right and left["selected_providers"][0]["provider_id"] == "vendor.b"


def test_priority_tie_uses_lexical_provider_id_and_lower_is_rejected():
    snapshot = discover_providers([descriptor("vendor.z", "z"), descriptor("vendor.a", "a")], domains=["cpu"])
    assert snapshot["selected_providers"][0]["provider_id"] == "vendor.a"
    assert snapshot["rejected_providers"][0]["reason"] == "lower_priority"


def test_duplicate_provider_and_detector_conflicts_fail_closed():
    different = discover_providers([descriptor("vendor.a"), descriptor("vendor.a", priority=101)], domains=["cpu"])
    assert different["selected_providers"] == [] and different["conflicts"][0]["kind"] == "duplicate_provider_id"
    detector = discover_providers([descriptor("vendor.a", "same"), descriptor("vendor.b", "same")], domains=["cpu"])
    assert detector["selected_providers"] == [] and {x["reason"] for x in detector["rejected_providers"]} == {"duplicate_detector_id"}
    same = descriptor("vendor.a")
    assert len(discover_providers([same, same], domains=["cpu"])["selected_providers"]) == 1


@pytest.mark.parametrize(("change", "reason"), [({"supported_platform_families": ["windows"]}, "unsupported_platform"), ({"supported_architectures": ["arm64"]}, "unsupported_architecture"), ({"supported_python_versions": ["3.11"]}, "unsupported_python"), ({"enabled": False}, "disabled")])
def test_compatibility_and_disabled_rejections(change, reason):
    snapshot = discover_providers([descriptor("vendor.a", **change)], domains=["cpu"], context={"platform_family": "linux", "architecture": "x86_64", "python_version": "3.12"})
    assert snapshot["rejected_providers"][0]["reason"] == reason


def test_malformed_sensitive_callable_and_non_finite_metadata_are_rejected():
    for metadata in ({"token": "secret"}, {"handler": lambda: None}, {"value": float("nan")}):
        with pytest.raises(DiscoveryError): normalize_descriptor(descriptor("vendor.a", metadata=metadata))


def test_binding_is_process_local_copy_safe_and_does_not_affect_identity_or_invoke():
    calls = []; provider = FakeProvider(calls); bindings = ProcessLocalProviderBindings(); bindings.register("vendor.a", provider)
    bound = discover_providers([descriptor("vendor.a")], domains=["cpu"], bindings=bindings)
    unbound = discover_providers([descriptor("vendor.a")], domains=["cpu"])
    assert bound["fingerprint"] == unbound["fingerprint"] and bound["discovery_id"] == unbound["discovery_id"]
    assert "FakeProvider" not in json.dumps(bound) and calls == []
    plan = discovery_to_detection_plan(bound, bindings); assert calls == []
    CapabilityDetectionOrchestrator.detect_from_discovery_plan(plan, ["cpu"]); assert calls == ["detect"]
    copied = json.loads(json.dumps(bound)); copied["selected_providers"][0]["provider_id"] = "changed"
    assert bindings.resolve("vendor.a") is provider


def test_unbound_adapts_to_safe_unavailable_only_when_explicitly_detected():
    bindings = ProcessLocalProviderBindings(); snapshot = discover_providers([descriptor("vendor.a")], domains=["cpu"], bindings=bindings)
    plan = discovery_to_detection_plan(snapshot, bindings)
    assert plan.providers == () and plan.unbound_selections[0]["binding_status"] == "unbound"
    result = CapabilityDetectionOrchestrator.detect_from_discovery_plan(plan, ["cpu"])
    assert result["results"][0]["status"] == "unavailable" and result["results"][0]["error_code"] == "provider_unbound"
