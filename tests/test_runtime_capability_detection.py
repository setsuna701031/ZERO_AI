from __future__ import annotations

import json

from core.runtime.runtime_capability_detection import CapabilityDetectionOrchestrator, DetectionContext, default_detector_providers


class FakeDetector:
    supported_platforms = ("any",)
    priority = 100
    def __init__(self, detector_id: str, domain: str, calls: list[str], *, broken: bool = False, status: str = "available"):
        self.detector_id, self.domain, self.calls, self.broken, self.status = detector_id, domain, calls, broken, status
    def detect(self, context: DetectionContext):
        self.calls.append(self.detector_id)
        if self.broken: raise RuntimeError("raw secret exception message")
        return {"detector_id": self.detector_id, "domain": self.domain, "status": self.status, "evidence": {"value": self.domain}, "error_code": None if self.status == "available" else "safe_unsupported", "provider": {"schema": "zero.runtime.capability_detector_provider.v1", "provider_version": 1, "detector_id": self.detector_id, "domain": self.domain, "priority": self.priority, "supported_platforms": ["any"]}}


def test_metadata_operations_do_not_invoke_and_explicit_detect_does():
    calls: list[str] = []; orchestrator = CapabilityDetectionOrchestrator([FakeDetector("cpu_a", "cpu", calls)])
    assert orchestrator.list_detectors()[0]["detector_id"] == "cpu_a"
    assert calls == []
    orchestrator.detect(["cpu"])
    assert calls == ["cpu_a"]


def test_registration_order_and_observation_time_do_not_affect_identity():
    left_calls: list[str] = []; right_calls: list[str] = []
    values = [FakeDetector("cpu_a", "cpu", left_calls), FakeDetector("model_a", "models", left_calls, status="unsupported")]
    left = CapabilityDetectionOrchestrator(values).detect(["models", "cpu"], observed_at="one")
    reversed_values = [FakeDetector("model_a", "models", right_calls, status="unsupported"), FakeDetector("cpu_a", "cpu", right_calls)]
    right = CapabilityDetectionOrchestrator(reversed_values).detect(["cpu", "models"], observed_at="two")
    assert left["fingerprint"] == right["fingerprint"] and left["detection_id"] == right["detection_id"]
    comparable_left, comparable_right = dict(left), dict(right)
    comparable_left["observed_at"] = comparable_right["observed_at"]
    assert comparable_left == comparable_right


def test_failure_is_isolated_and_raw_exception_or_provider_repr_never_leaks():
    calls: list[str] = []
    snapshot = CapabilityDetectionOrchestrator([FakeDetector("broken", "cpu", calls, broken=True), FakeDetector("models", "models", calls, status="unsupported")]).detect(["cpu", "models"])
    rendered = json.dumps(snapshot)
    assert snapshot["overall_status"] == "partial"
    assert snapshot["results"][0]["error_code"] == "detector_failed"
    assert "raw secret" not in rendered and "object at" not in rendered
    assert calls == ["broken", "models"]


def test_snapshot_is_copy_safe_and_canonical():
    calls: list[str] = []; orchestrator = CapabilityDetectionOrchestrator([FakeDetector("cpu", "cpu", calls)])
    first = orchestrator.detect(["cpu"]); first["results"][0]["evidence"]["value"] = "changed"
    assert orchestrator.detect(["cpu"])["results"][0]["evidence"]["value"] == "cpu"


def test_builtins_cover_all_domains_without_executing_on_construction():
    providers = default_detector_providers()
    assert {provider.domain for provider in providers} == {"cpu", "accelerator", "memory", "storage", "network", "power", "operating_system", "execution_environment", "tools", "models"}


def test_storage_missing_root_and_models_are_bounded():
    snapshot = CapabilityDetectionOrchestrator().detect(["models", "storage"])
    by_domain = {item["domain"]: item for item in snapshot["results"]}
    assert by_domain["storage"]["status"] == "unsupported"
    assert by_domain["models"]["evidence"] == {"models": []}


def test_storage_only_queries_caller_root_without_listing(monkeypatch, tmp_path):
    import core.runtime.runtime_capability_detection as detection
    queried = []
    monkeypatch.setattr(detection.shutil, "disk_usage", lambda path: queried.append(path) or detection.shutil._ntuple_diskusage(100, 40, 60))
    monkeypatch.setattr(detection.Path, "iterdir", lambda self: (_ for _ in ()).throw(AssertionError("directory scanned")))
    snapshot = CapabilityDetectionOrchestrator().detect(["storage"], workspace_root=tmp_path)
    assert queried == [tmp_path.resolve()] and snapshot["results"][0]["status"] == "available"


def test_tools_only_use_symbolic_lookup_and_never_execute(monkeypatch):
    import core.runtime.runtime_capability_detection as detection
    looked_up = []
    monkeypatch.setattr(detection.shutil, "which", lambda name: looked_up.append(name) or f"unsafe/full/{name}")
    snapshot = CapabilityDetectionOrchestrator().detect(["tools"])
    assert looked_up == ["git", "pytest", "python"]
    assert "unsafe/full" not in json.dumps(snapshot)
