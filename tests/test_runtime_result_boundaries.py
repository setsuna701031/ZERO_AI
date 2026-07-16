from __future__ import annotations

import json
import time
import tracemalloc
import pytest

from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_result_projection import (
    ProjectionAdapterRegistry,
    RUNTIME_RESULT_PROJECTION_ADAPTERS,
    RuntimeResultProjectionContract,
    bounded_json_projection,
)
from core.runtime.runtime_route_registry import RuntimeRouteRegistry


def test_bounded_projection_is_json_safe_and_recursive() -> None:
    value: dict[str, object] = {"items": list(range(100)), "text": "x" * 100}
    value["self"] = value

    projected = bounded_json_projection(value, max_depth=3, max_items=5, max_string_chars=12)

    assert projected["text"].endswith("<truncated>")
    assert projected["self"] == "<recursive_reference>"
    assert len(projected["items"]) == 6
    json.dumps(projected)


def test_registry_adds_metadata_to_detached_internal_result_without_public_sentinels(tmp_path) -> None:
    opaque = object()
    nested = {"large": opaque, "runtime": {"execution_path": {"owner": "runtime"}}}
    registry = RuntimeRouteRegistry()
    registry.register("bounded", lambda request, root, goal: lambda: {"ok": True, "nested": nested})

    result = registry.run("bounded", {}, tmp_path, "bounded route")

    assert result["nested"] is not nested
    assert result["nested"]["large"] is opaque
    assert result["nested"]["runtime"] is not nested["runtime"]
    assert result["nested"]["runtime"]["execution_path"]["owner"] == "runtime"
    assert "<max_depth_reached>" not in repr(result)
    assert result["runtime_route_registry_admission"] is True
    assert result["route"]["runtime_route_key"] == "bounded"


def test_mainline_persistence_uses_bounded_event_and_result_payloads(tmp_path) -> None:
    mainline = RuntimeNativeMainline.with_workspace(tmp_path)
    result = mainline.run_compatibility_entry(
        entrypoint="tests.bounded_persistence",
        runner=lambda: {"ok": True, "blob": "x" * (2 * 1024 * 1024)},
        goal="bounded persistence",
    )

    assert len(result["blob"]) == 2 * 1024 * 1024
    storage = tmp_path / "runtime_native_mainline" / "runtime_native_mainline.json"
    payload = json.loads(storage.read_text(encoding="utf-8"))
    assert storage.stat().st_size < 1024 * 1024
    assert "final_result" not in payload["events"][-1]["payload"]["result"]
    assert payload["runs"][-1]["final_result"]["blob"].endswith("<truncated>")


def test_projection_contract_fixes_identity_fields_limits_and_cycle_policy() -> None:
    contract = RuntimeResultProjectionContract(
        allowed_fields=("ok", "goal_id", "nested"),
        maximum_depth=3,
        maximum_items=4,
        maximum_string_chars=8,
    )
    source = {"ok": True, "goal_id": "goal-1", "hidden": "drop", "nested": {}}
    source["nested"]["cycle"] = source

    projected = contract.project(source)

    assert contract.identity == "zero.runtime_result_projection"
    assert contract.version == "v1"
    assert "hidden" not in projected
    assert projected["nested"]["cycle"] == "<recursive_reference>"


def test_projection_benchmark_500_goals_stays_fast_small_and_copy_free() -> None:
    deepcopy_calls = 0

    class CopyTrap(dict):
        def __deepcopy__(self, memo):
            nonlocal deepcopy_calls
            deepcopy_calls += 1
            raise AssertionError("projection_must_not_deepcopy")

    goals = [CopyTrap(goal_id=f"goal-{index}", summary="x" * 200, status="pending") for index in range(500)]
    source = CopyTrap(ok=True, goals=goals)
    source["cycle"] = source
    contract = RuntimeResultProjectionContract(maximum_items=500, maximum_depth=4)

    tracemalloc.start()
    started = time.perf_counter()
    projected = contract.project(source)
    elapsed_ms = (time.perf_counter() - started) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    encoded = json.dumps(projected, ensure_ascii=False).encode("utf-8")

    assert elapsed_ms <= 120
    assert peak_bytes <= 1024 * 1024
    assert len(encoded) <= 1024 * 1024
    assert deepcopy_calls == 0
    assert projected["cycle"] == "<recursive_reference>"


def test_projection_adapter_registry_is_extensible_without_runtime_changes() -> None:
    contract = RuntimeResultProjectionContract(allowed_fields=("ok", "value"))
    registry = ProjectionAdapterRegistry(contract)
    registry.register(
        "new_consumer",
        lambda value: {**value, "hidden": "drop"},
        adapter_id="projection-adapter:new-consumer:v1",
        owner_domain="tests",
        contract_version="v1",
        contract_hash=contract.contract_hash(),
        output_schema="NewConsumerProjection",
        max_payload_bytes=1024 * 1024,
        required_fields=("ok", "value"),
    )

    projected = registry.project("new_consumer", {"ok": True, "value": {"x": 1}})

    assert projected == {"ok": True, "value": {"x": 1}}
    assert registry.consumers() == ("new_consumer",)
    assert registry.manifest("new_consumer").output_schema == "NewConsumerProjection"
    assert registry.manifest("new_consumer").owner_domain == "tests"
    assert registry.manifest("new_consumer").contract_hash == contract.contract_hash()
    assert registry.compatibility_report("v1")["compatible"] == ("new_consumer",)
    assert registry.compatibility_report("v2")["upgrade_required"] == ("new_consumer",)
    assert registry.dependency_graph()["adapters"][0]["owner_domain"] == "tests"
    assert registry.upgrade_impact("v2")["affected_owner_domains"] == ("tests",)
    assert RUNTIME_RESULT_PROJECTION_ADAPTERS.consumers() == (
        "cli", "dashboard", "evidence", "memory", "persistence", "resume"
    )


def test_projection_adapter_registry_rejects_invalid_manifests_and_outputs() -> None:
    registry = ProjectionAdapterRegistry(RuntimeResultProjectionContract(maximum_size_bytes=1024))
    with pytest.raises(ValueError, match="contract_version_incompatible"):
        registry.register("future", adapter_id="future", owner_domain="tests", contract_version="v2", contract_hash=registry.contract.contract_hash(), output_schema="Future", max_payload_bytes=128)

    registry.register(
        "strict",
        adapter_id="projection-adapter:strict:v1",
        owner_domain="tests",
        contract_version="v1",
        contract_hash=registry.contract.contract_hash(),
        output_schema="StrictProjection",
        max_payload_bytes=128,
        required_fields=("ok",),
    )
    with pytest.raises(ValueError, match="required_fields_missing"):
        registry.project("strict", {"value": 1})
    with pytest.raises(ValueError, match="payload_limit_exceeded"):
        registry.project("strict", {"ok": True, "value": "x" * 120})
    health = registry.health()
    assert health["contract_coverage_percent"] == 100.0
    assert health["payload_violations"] == 1
    assert health["version_mismatch"] == 1
    assert health["schema_drift"] == 1
