from core.runtime.runtime_capability_detector import RuntimeCapabilityDetector
from core.runtime.runtime_capability_strategy import MAX_WORKERS_HARD_CAP, RuntimeCapabilityStrategy
from core.runtime.runtime_capability_strategy_selector import select_capability_strategy


def test_strategy_identity_copy_safety_and_json_serialization():
    profile = RuntimeCapabilityDetector([]).detect(detected_at="first").to_dict()
    first = select_capability_strategy(profile)
    profile["detected_at"] = "second"
    second = select_capability_strategy(profile)
    assert first["strategy_id"] == second["strategy_id"]
    assert first["fingerprint"] == second["fingerprint"]
    value = first.to_dict(); value["constraints"].append({"code": "changed"})
    assert {"code": "changed"} not in first["constraints"]
    assert '"schema"' in first.to_json()
    assert first["execution_preferences"]["parallelism"]["max_workers"] <= MAX_WORKERS_HARD_CAP


def test_strategy_builder_rejects_non_json_values():
    try: RuntimeCapabilityStrategy.create({"constraints": [{"code": {1}}]})
    except TypeError: pass
    else: raise AssertionError("set must not enter strategy")
