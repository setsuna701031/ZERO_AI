from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


ZERO_RUNTIME_AUTONOMOUS_EXECUTION_ENABLEMENT_SCHEMA = (
    "zero.runtime.autonomous_execution_enablement.v1"
)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    return bool(value is True)


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


@dataclass(frozen=True)
class RuntimeEnableTokenRecord:
    schema: str
    token_authorized: bool
    token_id: str
    token_identity: str
    denial_reason: str
    runtime_state_mutated: bool
    execution_started: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimePermissionLeaseRecord:
    schema: str
    lease_authorized: bool
    lease_id: str
    source_token_id: str
    lease_positive_ttl: bool
    ttl_seconds: int
    denial_reason: str
    runtime_state_mutated: bool
    execution_started: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeAutonomousStartGateRecord:
    schema: str
    autonomous_start_authorized: bool
    source_lease_id: str
    start_mode: str
    max_iterations: int
    safety_stop_enabled: bool
    loop_controller_enabled: bool
    tick_cycle_enabled: bool
    denial_reason: str
    runtime_state_mutated: bool
    execution_started: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeEmergencyStopRecord:
    schema: str
    emergency_stop_authorized: bool
    stop_token_id: str
    stop_reason: str
    active_runtime_id: str
    runtime_should_continue: bool
    runtime_state_mutated: bool
    execution_started: bool
    denial_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeLiveRuntimeSealRecord:
    schema: str
    live_runtime_authorized: bool
    source_start_id: str
    active_runtime_id: str
    emergency_stop_authorized: bool
    runtime_should_continue: bool
    denial_reason: str
    runtime_state_mutated: bool
    execution_started: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_runtime_enable_token(token_record: Any) -> dict[str, Any]:
    token = _mapping(token_record)
    token_id = _text(token.get("token_id") or token.get("runtime_enable_token_id"))
    token_identity = _text(token.get("token_identity") or token.get("identity"))
    purpose = _text(token.get("purpose") or token.get("token_purpose"))
    enabled = _truthy(token.get("runtime_enable_token_valid")) or _truthy(token.get("token_valid"))

    if not token:
        denial = "missing_enable_token"
        authorized = False
    elif not token_id:
        denial = "missing_token_id"
        authorized = False
    elif not token_identity:
        denial = "missing_token_identity"
        authorized = False
    elif purpose != "runtime_autonomous_start":
        denial = "invalid_token_purpose"
        authorized = False
    elif not enabled:
        denial = "token_not_valid"
        authorized = False
    else:
        denial = ""
        authorized = True

    return RuntimeEnableTokenRecord(
        schema=ZERO_RUNTIME_AUTONOMOUS_EXECUTION_ENABLEMENT_SCHEMA,
        token_authorized=authorized,
        token_id=token_id,
        token_identity=token_identity,
        denial_reason=denial,
        runtime_state_mutated=False,
        execution_started=False,
    ).to_dict()


def evaluate_execution_permission_lease(
    token_authorization_record: Any,
    lease_record: Any,
) -> dict[str, Any]:
    token = _mapping(token_authorization_record)
    lease = _mapping(lease_record)
    lease_id = _text(lease.get("lease_id") or lease.get("permission_lease_id"))
    source_token_id = _text(token.get("token_id") or lease.get("source_token_id"))
    ttl_seconds = _positive_int(lease.get("ttl_seconds") or lease.get("ttl"))

    if not token:
        denial = "missing_token_authorization"
        authorized = False
    elif not _truthy(token.get("token_authorized")):
        denial = "token_not_authorized"
        authorized = False
    elif not lease:
        denial = "missing_permission_lease"
        authorized = False
    elif not lease_id:
        denial = "missing_lease_id"
        authorized = False
    elif not source_token_id:
        denial = "missing_source_token_id"
        authorized = False
    elif ttl_seconds <= 0:
        denial = "non_positive_lease_ttl"
        authorized = False
    else:
        denial = ""
        authorized = True

    return RuntimePermissionLeaseRecord(
        schema=ZERO_RUNTIME_AUTONOMOUS_EXECUTION_ENABLEMENT_SCHEMA,
        lease_authorized=authorized,
        lease_id=lease_id,
        source_token_id=source_token_id,
        lease_positive_ttl=ttl_seconds > 0,
        ttl_seconds=ttl_seconds,
        denial_reason=denial,
        runtime_state_mutated=False,
        execution_started=False,
    ).to_dict()


def evaluate_autonomous_start_gate(
    lease_authorization_record: Any,
    loop_activation_record: Any | None = None,
    start_request: Any | None = None,
) -> dict[str, Any]:
    lease = _mapping(lease_authorization_record)
    loop = _mapping(loop_activation_record)
    request = _mapping(start_request)
    source_lease_id = _text(lease.get("lease_id"))
    start_mode = _text(request.get("start_mode") or "controlled_autonomous")
    max_iterations = _positive_int(request.get("max_iterations") or 1)
    safety_stop_enabled = request.get("safety_stop_enabled", True) is not False
    loop_controller_enabled = loop.get("loop_controller_enabled", True) is not False
    tick_cycle_enabled = loop.get("tick_cycle_enabled", True) is not False

    if not lease:
        denial = "missing_permission_lease_authorization"
        authorized = False
    elif not _truthy(lease.get("lease_authorized")):
        denial = "permission_lease_not_authorized"
        authorized = False
    elif not source_lease_id:
        denial = "missing_source_lease_id"
        authorized = False
    elif max_iterations <= 0:
        denial = "missing_positive_max_iterations"
        authorized = False
    elif not safety_stop_enabled:
        denial = "safety_stop_required"
        authorized = False
    elif not loop_controller_enabled:
        denial = "loop_controller_disabled"
        authorized = False
    elif not tick_cycle_enabled:
        denial = "tick_cycle_disabled"
        authorized = False
    else:
        denial = ""
        authorized = True

    return RuntimeAutonomousStartGateRecord(
        schema=ZERO_RUNTIME_AUTONOMOUS_EXECUTION_ENABLEMENT_SCHEMA,
        autonomous_start_authorized=authorized,
        source_lease_id=source_lease_id,
        start_mode=start_mode,
        max_iterations=max_iterations,
        safety_stop_enabled=safety_stop_enabled,
        loop_controller_enabled=loop_controller_enabled,
        tick_cycle_enabled=tick_cycle_enabled,
        denial_reason=denial,
        runtime_state_mutated=False,
        execution_started=False,
    ).to_dict()


def evaluate_emergency_stop_authority(
    stop_signal: Any,
    active_runtime_record: Any | None = None,
) -> dict[str, Any]:
    signal = _mapping(stop_signal)
    active = _mapping(active_runtime_record)
    stop_token_id = _text(signal.get("stop_token_id") or signal.get("emergency_stop_id"))
    stop_reason = _text(signal.get("stop_reason") or signal.get("reason"))
    active_runtime_id = _text(active.get("active_runtime_id") or signal.get("active_runtime_id"))
    requested = _truthy(signal.get("emergency_stop_requested")) or _truthy(signal.get("stop_requested"))

    if not signal:
        denial = "missing_emergency_stop_signal"
        authorized = False
    elif not requested:
        denial = "emergency_stop_not_requested"
        authorized = False
    elif not stop_token_id:
        denial = "missing_stop_token_id"
        authorized = False
    elif not stop_reason:
        denial = "missing_stop_reason"
        authorized = False
    else:
        denial = ""
        authorized = True

    return RuntimeEmergencyStopRecord(
        schema=ZERO_RUNTIME_AUTONOMOUS_EXECUTION_ENABLEMENT_SCHEMA,
        emergency_stop_authorized=authorized,
        stop_token_id=stop_token_id,
        stop_reason=stop_reason,
        active_runtime_id=active_runtime_id,
        runtime_should_continue=not authorized,
        runtime_state_mutated=False,
        execution_started=False,
        denial_reason=denial,
    ).to_dict()


def evaluate_live_runtime_seal(
    start_gate_record: Any,
    emergency_stop_record: Any | None = None,
) -> dict[str, Any]:
    start = _mapping(start_gate_record)
    stop = _mapping(emergency_stop_record)
    source_start_id = _text(start.get("source_lease_id"))
    active_runtime_id = _text(start.get("active_runtime_id") or source_start_id)
    stopped = _truthy(stop.get("emergency_stop_authorized"))

    if not start:
        denial = "missing_start_gate_record"
        authorized = False
    elif not _truthy(start.get("autonomous_start_authorized")):
        denial = "autonomous_start_not_authorized"
        authorized = False
    elif stopped:
        denial = "emergency_stop_authorized"
        authorized = False
    elif not source_start_id:
        denial = "missing_source_start_id"
        authorized = False
    else:
        denial = ""
        authorized = True

    return RuntimeLiveRuntimeSealRecord(
        schema=ZERO_RUNTIME_AUTONOMOUS_EXECUTION_ENABLEMENT_SCHEMA,
        live_runtime_authorized=authorized,
        source_start_id=source_start_id,
        active_runtime_id=active_runtime_id,
        emergency_stop_authorized=stopped,
        runtime_should_continue=authorized,
        denial_reason=denial,
        runtime_state_mutated=False,
        execution_started=False,
    ).to_dict()


__all__ = [
    "ZERO_RUNTIME_AUTONOMOUS_EXECUTION_ENABLEMENT_SCHEMA",
    "RuntimeEnableTokenRecord",
    "RuntimePermissionLeaseRecord",
    "RuntimeAutonomousStartGateRecord",
    "RuntimeEmergencyStopRecord",
    "RuntimeLiveRuntimeSealRecord",
    "evaluate_runtime_enable_token",
    "evaluate_execution_permission_lease",
    "evaluate_autonomous_start_gate",
    "evaluate_emergency_stop_authority",
    "evaluate_live_runtime_seal",
]
