from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import PurePath
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_configuration_validation import validate_runtime_integration_configuration
from core.runtime.runtime_capability_strategy_runtime_integration_decision import SCHEMA, STATUSES

@dataclass(frozen=True)
class RuntimeIntegrationDecisionValidationResult:
    valid: bool
    errors: tuple[str, ...]

_LINKS = ("source_configuration_id", "source_configuration_fingerprint", "source_integration_consumer_id", "source_integration_consumer_fingerprint", "source_integration_boundary_id", "source_integration_boundary_fingerprint", "source_consumption_id", "source_consumption_fingerprint", "source_wiring_id", "source_wiring_fingerprint", "source_bootstrap_configuration_id", "source_bootstrap_configuration_fingerprint", "source_runtime_decision_id", "source_strategy_id", "source_profile_id")
_REQUIRED = {"schema", "decision_id", "fingerprint", "status", "decision_payload", "reasons", "boundary", *_LINKS}
_BOUNDARY = {"sealed": True, "read_only": True, "passive_decision": True, "runtime_activation": False, "scope_expansion": False, "constraint_weakening": False, "authority_granted": False}
_FORBIDDEN = {"executor", "executor_target", "scheduler", "scheduler_queue", "planner", "planner_command", "mission", "mission_id", "agent", "agent_id", "approval", "approval_token", "authorization", "authorization_token", "mutation", "mutation_plan", "callback", "callable", "handler", "adapter", "provider", "plugin", "import_path", "command", "shell_command", "executable_command", "filesystem_path", "absolute_path", "environment_probe", "runtime_target", "runtime_component", "runtime_handle", "activation_flag", "activation_token", "runtime_started", "execution_authority", "mutation_authority", "approval_authority", "authorization_authority"}
_MARKERS = ("/", "\\", "\n", "\r", ";", "|", "&&", "$(", "`")

def _unsafe(value: Any) -> bool:
    if callable(value) or isinstance(value, float) and not math.isfinite(value) or isinstance(value, PurePath): return True
    if isinstance(value, Mapping): return any(k in _FORBIDDEN or (k in {"execution_started", "authority_granted"} and v is True) or _unsafe(v) for k, v in value.items())
    if isinstance(value, list): return any(_unsafe(v) for v in value)
    if isinstance(value, str): return any(m in value for m in _MARKERS)
    return not (value is None or isinstance(value, (str, bool, int)))

def _identity_valid(value: Mapping[str, Any]) -> bool:
    base = {k: v for k, v in value.items() if k not in {"decision_id", "fingerprint"}}
    expected = _identified(dict(base), "decision_id", "capability-strategy-runtime-integration-decision-")
    return value.get("decision_id") == expected["decision_id"] and value.get("fingerprint") == expected["fingerprint"]

def _boundary_valid(value: Mapping[str, Any]) -> bool: return value.get("boundary") == _BOUNDARY

def _monotonic(value: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    if value.get("source_configuration_id") != source.get("configuration_id") or value.get("source_configuration_fingerprint") != source.get("fingerprint"): return False
    if any(value.get(k) != source.get(k) for k in _LINKS[2:]): return False
    status = {"configured": "decided", "default_compatible": "default_compatible", "rejected": "rejected", "invalid": "invalid"}.get(source.get("status"))
    return value.get("status") == status and value.get("decision_payload") == (source.get("configuration_payload") if status == "decided" else None)

def validate_runtime_integration_decision(value: Any, source_configuration: Any = None) -> RuntimeIntegrationDecisionValidationResult:
    if not isinstance(value, Mapping): return RuntimeIntegrationDecisionValidationResult(False, ("decision_not_object",))
    errors = [f"missing:{k}" for k in sorted(_REQUIRED - set(value))] + [f"unexpected:{k}" for k in sorted(set(value) - _REQUIRED)]
    if value.get("schema") != SCHEMA or value.get("status") not in STATUSES: errors.append("invalid_contract")
    if value.get("status") == "decided":
        if not isinstance(value.get("decision_payload"), Mapping): errors.append("invalid_decision_payload")
    elif value.get("decision_payload") is not None: errors.append("unsafe_decision_payload")
    if not isinstance(value.get("reasons"), list) or not value.get("reasons") or not all(isinstance(x, str) and x for x in value.get("reasons", [])): errors.append("invalid_reasons")
    if not _boundary_valid(value) or _unsafe(value): errors.append("unsafe_boundary")
    try: valid_id = _identity_valid(value)
    except (TypeError, ValueError): valid_id = False
    if not valid_id: errors.append("identity_mismatch")
    if source_configuration is not None:
        if not isinstance(source_configuration, Mapping) or not validate_runtime_integration_configuration(source_configuration).valid: errors.append("invalid_source_configuration")
        elif not _monotonic(value, source_configuration): errors.append("source_configuration_mismatch")
    return RuntimeIntegrationDecisionValidationResult(not errors, tuple(dict.fromkeys(errors)))

__all__ = ["RuntimeIntegrationDecisionValidationResult", "validate_runtime_integration_decision"]
