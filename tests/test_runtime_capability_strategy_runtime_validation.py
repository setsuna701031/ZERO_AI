from copy import deepcopy

from core.runtime.runtime_capability_strategy_runtime_consumer import consume_capability_strategy
from core.runtime.runtime_capability_strategy_runtime_integration import integrate_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_runtime_validation import validate_consumer_result, validate_integration_result, validate_decision_record
from tests.capability_strategy_runtime_fixtures import strategy


def test_all_runtime_artifact_validators_and_fingerprint_tampering():
    value = strategy()
    artifacts = [(consume_capability_strategy(value), validate_consumer_result), (integrate_capability_strategy_runtime(value), validate_integration_result), (decide_capability_strategy_runtime(value), validate_decision_record)]
    for artifact, validator in artifacts:
        assert validator(artifact).valid
        changed = deepcopy(artifact); changed["fingerprint"] = "0" * 64
        assert not validator(changed).valid


def test_strategy_schema_fingerprint_and_required_fields_fail_closed():
    for mutation in ("schema", "fingerprint", "profile_id"):
        value = strategy()
        if mutation == "schema": value[mutation] = "invalid"
        elif mutation == "fingerprint": value[mutation] = "0" * 64
        else: del value[mutation]
        assert consume_capability_strategy(value)["status"] == "invalid"
