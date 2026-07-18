from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_consumer import consume_runtime_strategy_decision
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_decision import decide_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_validation import validate_bootstrap_consumer, validate_bootstrap_configuration, validate_bootstrap_decision
from tests.capability_strategy_runtime_fixtures import strategy


def test_artifact_validators_identity_and_source_monotonicity():
    source = decide_capability_strategy_runtime(strategy("accelerator_available", workers=4, compute="accelerator", tools=("python",)))
    artifacts = [(consume_runtime_strategy_decision(source), validate_bootstrap_consumer), (configure_capability_strategy_bootstrap(source), validate_bootstrap_configuration), (decide_capability_strategy_bootstrap(source), validate_bootstrap_decision)]
    for artifact, validator in artifacts:
        assert validator(artifact, source).valid
        changed = deepcopy(artifact); changed["fingerprint"] = "0" * 64
        assert not validator(changed, source).valid


def test_monotonic_validator_rejects_worker_tools_network_and_accelerator_expansion():
    source = decide_capability_strategy_runtime(strategy(workers=2, tools=("python",)))
    original = consume_runtime_strategy_decision(source)
    for key, expanded in (("worker_limit", 3), ("available_tools", ["python", "new"]), ("network_mode", "unrestricted"), ("accelerator_mode", "cuda")):
        changed = deepcopy(original); changed["configuration_fields"][key] = expanded
        from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
        changed = _identified({k: v for k, v in changed.items() if k not in {"consumer_id", "fingerprint"}}, "consumer_id", "capability-strategy-bootstrap-consumer-")
        result = validate_bootstrap_consumer(changed, source)
        assert not result.valid and "monotonic_restriction_violation" in result.errors


def test_invalid_schema_fingerprint_and_missing_fields_fail_closed():
    source = decide_capability_strategy_runtime(strategy())
    variants = []
    for key in ("schema", "fingerprint", "status"):
        changed = deepcopy(source)
        if key == "schema": changed[key] = "invalid"
        elif key == "fingerprint": changed[key] = "0" * 64
        else: del changed[key]
        variants.append(changed)
    assert all(consume_runtime_strategy_decision(value)["status"] == "rejected" for value in variants)
