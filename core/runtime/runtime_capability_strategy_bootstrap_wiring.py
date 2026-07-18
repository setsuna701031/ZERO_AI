from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_bootstrap_validation import validate_bootstrap_configuration


REQUEST_SCHEMA = "zero.runtime.capability_strategy_bootstrap_wiring_request.v1"
RESULT_SCHEMA = "zero.runtime.capability_strategy_bootstrap_wiring_result.v1"
TARGET_STAGES = frozenset({"plan", "integration", "consumer"})
STATUSES = frozenset({"wired", "disabled", "default_compatible", "rejected", "invalid"})


def build_bootstrap_wiring_request(*, bootstrap_configuration: Any = None, target_bootstrap_stage: str = "plan", enabled: bool = True, compatibility_mode: bool | None = None) -> dict[str, Any]:
    if compatibility_mode is None:
        compatibility_mode = bootstrap_configuration is None or (isinstance(bootstrap_configuration, Mapping) and bootstrap_configuration.get("status") == "default_compatible")
    base = {
        "schema": REQUEST_SCHEMA, "enabled": enabled,
        "bootstrap_configuration": deepcopy(bootstrap_configuration),
        "target_bootstrap_stage": target_bootstrap_stage,
        "compatibility_mode": compatibility_mode,
    }
    return _identified(base, "request_id", "capability-strategy-bootstrap-wiring-request-")


def _source_linkage(configuration: Any) -> dict[str, Any]:
    if not isinstance(configuration, Mapping): configuration = {}
    runtime = configuration.get("source_runtime_decision_linkage") if isinstance(configuration.get("source_runtime_decision_linkage"), Mapping) else {}
    strategy = configuration.get("source_strategy_linkage") if isinstance(configuration.get("source_strategy_linkage"), Mapping) else {}
    return {
        "source_bootstrap_configuration_id": configuration.get("configuration_id"),
        "source_bootstrap_configuration_fingerprint": configuration.get("fingerprint"),
        "source_runtime_decision_id": runtime.get("decision_id"),
        "source_strategy_id": strategy.get("strategy_id"),
        "source_profile_id": strategy.get("profile_id"),
    }


def _effective_options(configuration: Mapping[str, Any]) -> dict[str, Any]:
    fields = configuration["configuration"]
    return {
        "bootstrap_mode": fields["bootstrap_mode"], "execution_mode": fields["execution_mode"],
        "worker_limit": fields["worker_limit"], "network_mode": fields["network_mode"],
        "resource_mode": fields["resource_mode"], "accelerator_mode": fields["accelerator_mode"],
        "available_tools": sorted(set(fields["available_tools"]), key=str.casefold),
    }


def wire_capability_strategy_bootstrap(request: Any) -> dict[str, Any]:
    from core.runtime.runtime_capability_strategy_bootstrap_wiring_validation import validate_wiring_request

    request_valid = validate_wiring_request(request).valid
    configuration = request.get("bootstrap_configuration") if isinstance(request, Mapping) else None
    linkage = _source_linkage(configuration)
    enabled = request.get("enabled") if isinstance(request, Mapping) else False
    target = request.get("target_bootstrap_stage") if isinstance(request, Mapping) else None
    compatibility = request.get("compatibility_mode") if isinstance(request, Mapping) else False
    if not request_valid:
        status, applied, options, reasons = "invalid", False, None, ["invalid_wiring_request"]
    elif not enabled:
        status, applied, options, reasons = "disabled", False, None, ["optional_wiring_disabled"]
    elif configuration is None:
        status, applied, options, reasons, compatibility = "default_compatible", False, None, ["configuration_unavailable"], True
    elif not validate_bootstrap_configuration(configuration).valid or configuration.get("status") == "rejected":
        status, applied, options, reasons = "rejected", False, None, ["bootstrap_configuration_rejected"]
    elif configuration.get("status") == "default_compatible":
        status, applied, options, reasons, compatibility = "default_compatible", False, None, ["default_compatible_configuration"], True
    else:
        status, applied, options, reasons = "wired", True, _effective_options(configuration), ["bounded_configuration_wired"]
    base = {
        "schema": RESULT_SCHEMA, "status": status, "enabled": bool(enabled),
        "target_bootstrap_stage": target, "configuration_applied": applied,
        "effective_bootstrap_options": options, **linkage,
        "compatibility_mode": bool(compatibility), "reasons": reasons,
        "decision_input_only": True, "authority_granted": False,
        "executor_ownership_changed": False, "runtime_started": False,
    }
    return _identified(base, "wiring_id", "capability-strategy-bootstrap-wiring-")


def run_existing_bootstrap_builder(
    builder: Callable[..., dict[str, Any]], *, builder_kwargs: Mapping[str, Any],
    wiring_request: Any = None,
    option_translator: Callable[[dict[str, Any], dict[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply ephemeral options, then return only the existing builder's artifact."""
    kwargs = deepcopy(dict(builder_kwargs))
    if wiring_request is not None:
        wiring = wire_capability_strategy_bootstrap(wiring_request)
        if wiring["status"] in {"invalid", "rejected"}: raise ValueError("bootstrap_wiring_rejected")
        if wiring["configuration_applied"]:
            if option_translator is None: raise ValueError("option_translator_required")
            translated = option_translator(deepcopy(wiring["effective_bootstrap_options"]), deepcopy(kwargs))
            if not isinstance(translated, Mapping): raise TypeError("invalid_translated_builder_options")
            kwargs = deepcopy(dict(translated))
    return builder(**kwargs)


__all__ = ["REQUEST_SCHEMA", "RESULT_SCHEMA", "TARGET_STAGES", "STATUSES", "build_bootstrap_wiring_request", "wire_capability_strategy_bootstrap", "run_existing_bootstrap_builder"]
