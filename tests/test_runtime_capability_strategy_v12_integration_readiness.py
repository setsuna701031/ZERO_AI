from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from core.runtime.runtime_capability_strategy import canonical_json
from core.runtime.runtime_capability_strategy_runtime_consumer import consume_capability_strategy
from core.runtime.runtime_capability_strategy_runtime_integration import integrate_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_runtime_validation import (
    validate_consumer_result,
    validate_decision_record,
    validate_integration_result,
)
from core.runtime.runtime_capability_strategy_bootstrap_consumer import consume_runtime_strategy_decision
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_decision import decide_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_validation import (
    validate_bootstrap_configuration,
    validate_bootstrap_consumer,
    validate_bootstrap_decision,
)
from core.runtime.runtime_capability_strategy_bootstrap_wiring import (
    build_bootstrap_wiring_request,
    run_existing_bootstrap_builder,
    wire_capability_strategy_bootstrap,
)
from core.runtime.runtime_capability_strategy_bootstrap_wiring_validation import (
    validate_wiring_request,
    validate_wiring_result,
)
from tests.capability_strategy_runtime_fixtures import strategy


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MODULES = (
    "runtime_capability_strategy_runtime_consumer.py",
    "runtime_capability_strategy_runtime_integration.py",
    "runtime_capability_strategy_runtime_decision.py",
    "runtime_capability_strategy_runtime_validation.py",
    "runtime_capability_strategy_bootstrap_consumer.py",
    "runtime_capability_strategy_bootstrap_configuration.py",
    "runtime_capability_strategy_bootstrap_decision.py",
    "runtime_capability_strategy_bootstrap_validation.py",
    "runtime_capability_strategy_bootstrap_wiring.py",
    "runtime_capability_strategy_bootstrap_wiring_validation.py",
)
EXPECTED_SCHEMAS = {
    "zero.runtime.capability_strategy_runtime_consumer.v1",
    "zero.runtime.capability_strategy_runtime_integration.v1",
    "zero.runtime.capability_strategy_runtime_decision.v1",
    "zero.runtime.capability_strategy_bootstrap_consumer.v1",
    "zero.runtime.capability_strategy_bootstrap_configuration.v1",
    "zero.runtime.capability_strategy_bootstrap_decision.v1",
    "zero.runtime.capability_strategy_bootstrap_wiring_request.v1",
    "zero.runtime.capability_strategy_bootstrap_wiring_result.v1",
}


def _chain(source=None, *, enabled=True):
    source = strategy(tools=("zeta", "Alpha", "alpha")) if source is None else source
    consumer = consume_capability_strategy(source, enabled=enabled)
    integration = integrate_capability_strategy_runtime(source, enabled=enabled)
    runtime_decision = decide_capability_strategy_runtime(source, enabled=enabled)
    bootstrap_consumer = consume_runtime_strategy_decision(runtime_decision)
    configuration = configure_capability_strategy_bootstrap(runtime_decision)
    bootstrap_decision = decide_capability_strategy_bootstrap(runtime_decision)
    request = build_bootstrap_wiring_request(bootstrap_configuration=configuration)
    wiring = wire_capability_strategy_bootstrap(request)
    return consumer, integration, runtime_decision, bootstrap_consumer, configuration, bootstrap_decision, request, wiring


def test_canonical_inventory_is_unique_complete_and_dependency_bounded():
    schemas = []
    forbidden_fragments = (
        "mission", "goal", "agent", "scheduler", "executor", "daemon",
        "autonomous", "mutation", "approval", "authorization", "token", "activation",
    )
    for filename in PRODUCTION_MODULES:
        path = ROOT / "core" / "runtime" / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str) and node.value.value.startswith("zero.runtime.capability_strategy_"):
                    schemas.append(node.value.value)
            if isinstance(node, ast.ImportFrom):
                imported = (node.module or "").casefold()
                assert not any(fragment in imported for fragment in forbidden_fragments)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name.casefold()
                    assert not any(fragment in imported for fragment in forbidden_fragments)
    assert set(schemas) == EXPECTED_SCHEMAS
    assert len(schemas) == len(set(schemas))


def test_end_to_end_chain_is_deterministic_linked_valid_and_authority_free():
    first = _chain()
    second = _chain()
    assert first == second
    consumer, integration, runtime_decision, bootstrap_consumer, configuration, bootstrap_decision, request, wiring = first
    validations = (
        validate_consumer_result(consumer), validate_integration_result(integration),
        validate_decision_record(runtime_decision), validate_bootstrap_consumer(bootstrap_consumer, runtime_decision),
        validate_bootstrap_configuration(configuration, runtime_decision),
        validate_bootstrap_decision(bootstrap_decision, runtime_decision),
        validate_wiring_request(request), validate_wiring_result(wiring, configuration),
    )
    assert all(result.valid for result in validations)
    assert [item.get("status") for item in first] == [
        "consumed", "integrated", "accepted", "consumed", "configured", "accepted", None, "wired"
    ]
    assert integration["consumer_result_linkage"] == {"consumer_id": consumer["consumer_id"], "fingerprint": consumer["fingerprint"]}
    assert runtime_decision["integration_linkage"] == {"integration_id": integration["integration_id"], "fingerprint": integration["fingerprint"]}
    assert configuration["source_runtime_decision_linkage"] == {"decision_id": runtime_decision["decision_id"], "fingerprint": runtime_decision["fingerprint"]}
    assert wiring["source_bootstrap_configuration_id"] == configuration["configuration_id"]
    assert wiring["source_strategy_id"] == runtime_decision["strategy_linkage"]["strategy_id"]
    assert wiring["source_profile_id"] == runtime_decision["strategy_linkage"]["profile_id"]
    assert consumer["runtime_directives"]["available_tools"] == sorted(
        set(consumer["runtime_directives"]["available_tools"]), key=str.casefold
    )
    assert all(canonical_json(item) == canonical_json(json.loads(canonical_json(item))) for item in first)
    for artifact in first:
        text = canonical_json(artifact).casefold()
        assert all(term not in text for term in ("authorized", "approval", "token", "activated", "execution_evidence"))
    assert wiring["decision_input_only"] is True and wiring["authority_granted"] is False
    assert wiring["executor_ownership_changed"] is False and wiring["runtime_started"] is False


def test_status_default_rejection_and_monotonic_closure():
    fallback = _chain(strategy("unknown_capability", workers=8, tools=("python", "shell")))
    assert [item.get("status") for item in fallback] == [
        "fallback", "fallback", "degraded", "fallback", "degraded", "degraded", None, "wired"
    ]
    options = fallback[-1]["effective_bootstrap_options"]
    assert options["worker_limit"] == 1 and options["execution_mode"] == "cpu_only"
    assert options["network_mode"] == "offline_safe" and options["accelerator_mode"] == "disabled"
    assert set(options["available_tools"]) <= {"python", "shell"}

    compatible = _chain(None, enabled=False)
    assert [item.get("status") for item in compatible] == [
        "default_compatible", "default_compatible", "default_compatible", "default_compatible",
        "default_compatible", "default_compatible", None, "default_compatible",
    ]
    assert compatible[-1]["effective_bootstrap_options"] is None

    rejected = _chain({})
    assert [item.get("status") for item in rejected] == [
        "invalid", "invalid", "rejected", "rejected", "rejected", "rejected", None, "rejected"
    ]
    assert rejected[-1]["configuration_applied"] is False
    assert rejected[-1]["effective_bootstrap_options"] is None


def test_optional_wiring_is_detached_and_default_path_preserves_existing_builder_bytes():
    configuration = _chain()[4]
    frozen = deepcopy(configuration)
    request = build_bootstrap_wiring_request(bootstrap_configuration=configuration)
    request_frozen = deepcopy(request)
    wiring = wire_capability_strategy_bootstrap(request)
    assert configuration == frozen and request == request_frozen
    wiring["reasons"].append("local_mutation")
    assert configuration == frozen and request == request_frozen

    def existing_builder(*, payload="unchanged"):
        base = {"schema": "existing.bootstrap.builder.v1", "payload": payload}
        fingerprint = hashlib.sha256(canonical_json(base).encode("utf-8")).hexdigest()
        return {**base, "artifact_id": "existing-" + fingerprint[:24], "fingerprint": fingerprint}

    direct = existing_builder()
    absent = run_existing_bootstrap_builder(existing_builder, builder_kwargs={})
    disabled = run_existing_bootstrap_builder(
        existing_builder,
        builder_kwargs={},
        wiring_request=build_bootstrap_wiring_request(bootstrap_configuration=configuration, enabled=False),
    )
    assert canonical_json(direct) == canonical_json(absent) == canonical_json(disabled)
    assert direct["artifact_id"] == absent["artifact_id"] == disabled["artifact_id"]
    assert direct["fingerprint"] == absent["fingerprint"] == disabled["fingerprint"]
    assert not any(key.startswith(("wiring", "source_")) for key in absent)
