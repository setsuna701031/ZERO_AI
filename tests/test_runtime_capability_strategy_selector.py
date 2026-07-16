from copy import deepcopy

from core.runtime.runtime_capability_detector import RuntimeCapabilityDetector
from core.runtime.runtime_capability_profile import RuntimeCapabilityProfile
from core.runtime.runtime_capability_strategy import LOW_MEMORY_AVAILABLE_BYTES, LOW_STORAGE_FREE_BYTES, MAX_WORKERS_HARD_CAP
from core.runtime.runtime_capability_strategy_selector import select_capability_strategy


def profile_with(**sections):
    value = RuntimeCapabilityDetector().detect(detected_at="stable").to_dict()
    value.update(deepcopy(sections))
    return RuntimeCapabilityProfile.create(value, detected_at=value["detected_at"]).to_dict()


def test_cpu_fallback_unknown_cores_memory_and_offline_safe():
    profile = profile_with(cpu={"logical_cores": 0}, accelerators=[], memory={"total_bytes": None, "available_bytes": None})
    strategy = select_capability_strategy(profile).to_dict()
    assert strategy["recommended_mode"] == "cpu_only"
    assert strategy["execution_preferences"]["parallelism"]["max_workers"] == 1
    assert strategy["execution_preferences"]["memory_policy"]["mode"] == "conservative"
    assert strategy["execution_preferences"]["network_policy"] == {"mode": "offline_safe", "outbound_required": False}


def test_accelerator_low_memory_low_storage_and_worker_cap_rules():
    accelerator = {"kind": "gpu", "vendor": "any", "name": "device", "backend": "generic", "available": True, "memory_bytes": None, "metadata": {}}
    accelerated = select_capability_strategy(profile_with(cpu={"logical_cores": 100}, accelerators=[accelerator])).to_dict()
    assert accelerated["recommended_mode"] == "accelerator_available"
    assert accelerated["execution_preferences"]["preferred_compute"] == "accelerator"
    assert accelerated["execution_preferences"]["parallelism"]["max_workers"] == MAX_WORKERS_HARD_CAP
    assert select_capability_strategy(profile_with(memory={"total_bytes": LOW_MEMORY_AVAILABLE_BYTES, "available_bytes": LOW_MEMORY_AVAILABLE_BYTES - 1}))["recommended_mode"] == "memory_constrained"
    storage = [{"path": "safe", "total_bytes": LOW_STORAGE_FREE_BYTES * 2, "free_bytes": LOW_STORAGE_FREE_BYTES - 1}]
    assert select_capability_strategy(profile_with(storage=storage))["recommended_mode"] == "storage_constrained"


def test_tools_models_power_and_input_mutation():
    source = profile_with(
        available_tools=[{"name": "z", "available": True}, {"name": "missing", "available": False}, {"name": "a", "available": True}],
        installed_models=[{"provider": "p", "name": "z"}, {"provider": "p", "name": "a"}],
        power={"source": "battery", "battery_present": True, "constrained": True},
    )
    strategy = select_capability_strategy(source)
    source["available_tools"].clear()
    assert strategy["tool_preferences"] == [{"name": "a"}, {"name": "z"}]
    assert {"code": "unavailable_tools"} in strategy["constraints"]
    assert strategy["model_preferences"] == [{"name": "a", "provider": "p"}, {"name": "z", "provider": "p"}]
    assert strategy["execution_preferences"]["preferred_compute"] == "cpu"
    assert strategy["execution_preferences"]["parallelism"]["max_workers"] <= 2


def test_invalid_profile_is_bounded_fail_safe_without_sensitive_details():
    strategy = select_capability_strategy({"credential": "secret"}).to_dict()
    assert strategy["recommended_mode"] == "unknown_capability"
    assert strategy["diagnostics"] == [{"code": "profile_validation_failed"}]
    assert "secret" not in str(strategy)
