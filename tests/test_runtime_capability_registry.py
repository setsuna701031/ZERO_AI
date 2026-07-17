from __future__ import annotations

import json

import pytest

from core.runtime.runtime_capability_registry import RegistryError, RuntimeCapabilityRegistry, build_default_capability_registry


def entry(name: str, domain: str, *, priority: int = 100, enabled: bool = True):
    return {"name": name, "kind": "detector", "capability_domain": domain, "provider_type": "adapter", "provider_ref": f"example.adapters:{name.title().replace('_', '')}", "priority": priority, "enabled": enabled, "metadata": {"stable": True}}


def test_identity_and_snapshot_are_registration_order_independent():
    values = [entry("cpu", "cpu"), entry("memory", "memory"), entry("gpu", "accelerator")]
    left, right = RuntimeCapabilityRegistry(), RuntimeCapabilityRegistry()
    for value in values: left.register(value)
    for value in reversed(values): right.register(value)
    assert left.snapshot() == right.snapshot()


def test_provider_object_is_never_serialized_or_used_in_identity():
    first, second = RuntimeCapabilityRegistry(), RuntimeCapabilityRegistry()
    first.register(entry("cpu", "cpu"), provider=object())
    second.register(entry("cpu", "cpu"), provider=object())
    assert first.snapshot() == second.snapshot()
    rendered = json.dumps(first.snapshot())
    assert "object at" not in rendered


def test_mutable_inputs_and_snapshots_are_detached():
    value = entry("cpu", "cpu"); value["metadata"]["items"] = [1]
    registry = RuntimeCapabilityRegistry(); registered = registry.register(value)
    value["metadata"]["items"].append(2); registered["metadata"]["items"].append(3)
    snapshot = registry.snapshot(); snapshot["entries"][0]["metadata"]["items"].append(4)
    assert registry.snapshot()["entries"][0]["metadata"]["items"] == [1]


def test_resolve_is_enabled_priority_ordered_and_stably_tied():
    registry = RuntimeCapabilityRegistry()
    registry.register(entry("low", "cpu", priority=10), provider="low")
    registry.register(entry("high", "cpu", priority=900), provider="high")
    registry.register(entry("disabled", "cpu", priority=1000, enabled=False), provider="disabled")
    result = registry.resolve("detector", "cpu")
    assert result is not None and result.entry["name"] == "high" and result.provider == "high"


def test_duplicate_is_idempotent_and_invalid_registration_is_atomic():
    registry = RuntimeCapabilityRegistry(); value = entry("cpu", "cpu")
    assert registry.register(value) == registry.register(value)
    before = registry.snapshot()
    with pytest.raises(RegistryError): registry.register({**value, "priority": 1001})
    assert registry.snapshot() == before


def test_default_builder_is_fresh_and_does_not_execute_adapters(monkeypatch):
    from core.runtime import runtime_capability_adapters as adapters
    monkeypatch.setattr(adapters.CPUAdapter, "detect", lambda self: pytest.fail("detect called"))
    first, second = build_default_capability_registry(), build_default_capability_registry()
    assert first is not second
    assert {item["capability_domain"] for item in first.list_entries("detector")} == {"os", "cpu", "memory", "storage", "accelerator", "tool", "model", "execution_environment", "power"}

