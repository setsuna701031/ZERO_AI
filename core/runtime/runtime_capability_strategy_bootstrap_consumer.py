from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_validation import validate_decision_record


SCHEMA = "zero.runtime.capability_strategy_bootstrap_consumer.v1"
STATUSES = frozenset({"consumed", "fallback", "default_compatible", "rejected"})


def _linkage(decision: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(decision, Mapping):
        return ({"decision_id": None, "fingerprint": None}, {"strategy_id": None, "fingerprint": None, "profile_id": None, "profile_fingerprint": None})
    strategy = decision.get("strategy_linkage") if isinstance(decision.get("strategy_linkage"), Mapping) else {}
    return (
        {"decision_id": decision.get("decision_id"), "fingerprint": decision.get("fingerprint")},
        deepcopy(dict(strategy)),
    )


def build_bootstrap_configuration_fields(decision: Mapping[str, Any]) -> dict[str, Any] | None:
    status = decision["status"]
    if status == "rejected": return None
    if status == "default_compatible":
        return {
            "bootstrap_mode": "default_compatible", "execution_mode": None, "worker_limit": None,
            "network_mode": None, "resource_mode": None, "accelerator_mode": None,
            "available_tools": [], "compatibility_mode": True, "fallback_applied": False,
            "source_runtime_decision_id": decision["decision_id"],
            "source_runtime_decision_fingerprint": decision["fingerprint"],
            "source_strategy_id": decision["strategy_linkage"]["strategy_id"],
            "source_strategy_fingerprint": decision["strategy_linkage"]["fingerprint"],
        }
    directives = decision["accepted_directives"]
    fallback = status == "degraded"
    return {
        "bootstrap_mode": "safe_fallback" if fallback else "strategy_guided",
        "execution_mode": directives["execution_mode"], "worker_limit": directives["worker_limit"],
        "network_mode": directives["network_mode"], "resource_mode": directives["resource_mode"],
        "accelerator_mode": directives["accelerator_mode"],
        "available_tools": sorted(set(directives["available_tools"]), key=str.casefold),
        "compatibility_mode": False, "fallback_applied": fallback,
        "source_runtime_decision_id": decision["decision_id"],
        "source_runtime_decision_fingerprint": decision["fingerprint"],
        "source_strategy_id": directives["source_strategy_id"],
        "source_strategy_fingerprint": directives["source_strategy_fingerprint"],
    }


def consume_runtime_strategy_decision(decision: Any) -> dict[str, Any]:
    decision_linkage, strategy_linkage = _linkage(decision)
    if not validate_decision_record(decision).valid:
        status, fields, reasons = "rejected", None, ["invalid_runtime_decision"]
    else:
        status = {"accepted": "consumed", "degraded": "fallback", "default_compatible": "default_compatible", "rejected": "rejected"}[decision["status"]]
        fields = build_bootstrap_configuration_fields(decision)
        reasons = deepcopy(decision["reasons"]) if status != "rejected" else ["runtime_decision_rejected"]
    base = {
        "schema": SCHEMA, "status": status, "configuration_fields": fields,
        "source_runtime_decision_linkage": decision_linkage, "source_strategy_linkage": strategy_linkage,
        "reasons": reasons, "decision_input_only": True, "authority_granted": False,
        "executor_ownership_changed": False,
    }
    return _identified(base, "consumer_id", "capability-strategy-bootstrap-consumer-")


__all__ = ["SCHEMA", "STATUSES", "build_bootstrap_configuration_fields", "consume_runtime_strategy_decision"]
