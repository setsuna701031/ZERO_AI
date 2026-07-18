from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_bootstrap_wiring_validation import validate_wiring_result


SCHEMA = "zero.runtime.capability_strategy_bootstrap_consumption.v1"
STATUSES = frozenset({"consumed", "default_compatible", "rejected", "invalid"})


def _linkage(wiring: Any) -> dict[str, Any]:
    if not isinstance(wiring, Mapping):
        wiring = {}
    return {
        "source_wiring_id": wiring.get("wiring_id"),
        "source_wiring_fingerprint": wiring.get("fingerprint"),
        "source_bootstrap_configuration_id": wiring.get("source_bootstrap_configuration_id"),
        "source_bootstrap_configuration_fingerprint": wiring.get("source_bootstrap_configuration_fingerprint"),
        "source_runtime_decision_id": wiring.get("source_runtime_decision_id"),
        "source_strategy_id": wiring.get("source_strategy_id"),
        "source_profile_id": wiring.get("source_profile_id"),
    }


def consume_capability_strategy_bootstrap_wiring(wiring: Any) -> dict[str, Any]:
    valid = validate_wiring_result(wiring).valid
    source_status = wiring.get("status") if isinstance(wiring, Mapping) else None
    if not valid:
        status, payload, reasons = "invalid", None, ["invalid_bootstrap_wiring"]
    elif source_status == "wired":
        status = "consumed"
        payload = {
            "target_bootstrap_stage": wiring["target_bootstrap_stage"],
            "effective_bootstrap_options": deepcopy(wiring["effective_bootstrap_options"]),
        }
        reasons = ["validated_bootstrap_wiring_consumed"]
    elif source_status in {"disabled", "default_compatible"}:
        status, payload, reasons = "default_compatible", None, ["bootstrap_wiring_not_consumable"]
    elif source_status == "rejected":
        status, payload, reasons = "rejected", None, ["bootstrap_wiring_rejected"]
    else:
        status, payload, reasons = "invalid", None, ["invalid_bootstrap_wiring"]
    base = {
        "schema": SCHEMA,
        "status": status,
        **_linkage(wiring),
        "consumer_payload": payload,
        "reasons": reasons,
        "boundary": {
            "read_only": True,
            "consumer_input_only": True,
            "runtime_activation": False,
            "scope_expansion": False,
        },
    }
    return _identified(base, "consumption_id", "capability-strategy-bootstrap-consumption-")


__all__ = ["SCHEMA", "STATUSES", "consume_capability_strategy_bootstrap_wiring"]
