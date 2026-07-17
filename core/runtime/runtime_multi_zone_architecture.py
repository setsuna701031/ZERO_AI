from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


ZONE_MAIN = "main_runtime"
ZONE_REPAIR = "repair_runtime"
ZONE_MUTATION = "mutation_runtime"
ZONE_SANDBOX = "sandbox_runtime"
ZONE_REPLAY = "replay_runtime"

ZONE_STATUS_ACTIVE = "active"
ZONE_STATUS_ISOLATED = "isolated"
ZONE_STATUS_DEGRADED = "degraded"

ROUTE_ALLOWED = "allowed"
ROUTE_REDIRECTED = "redirected"
ROUTE_BLOCKED = "blocked"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeZone:
    zone_id: str
    zone_name: str
    status: str
    allowed_step_types: list[str]
    isolated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "status": self.status,
            "allowed_step_types": list(self.allowed_step_types),
            "isolated": self.isolated,
        }


@dataclass(frozen=True)
class RuntimeZoneRoutingDecision:
    route_status: str
    selected_zone: str
    execution_allowed: bool
    reason: str
    runtime_zones: list[dict[str, Any]]
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_zone_routing_decision",
            "route_status": self.route_status,
            "selected_zone": self.selected_zone,
            "execution_allowed": self.execution_allowed,
            "reason": self.reason,
            "runtime_zones": copy.deepcopy(self.runtime_zones),
            "created_at": self.created_at,
        }

        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()

        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(
            self.to_dict(include_fingerprint=False)
        )


class RuntimeMultiZoneArchitecture:
    """
    Multi-zone runtime topology.

    Splits execution responsibilities across isolated runtime zones
    to reduce cross-runtime corruption spread.
    """

    def __init__(self) -> None:
        self.zones = {
            ZONE_MAIN: RuntimeZone(
                zone_id="zone-main",
                zone_name=ZONE_MAIN,
                status=ZONE_STATUS_ACTIVE,
                allowed_step_types=["tool", "command", "task"],
            ),
            ZONE_REPAIR: RuntimeZone(
                zone_id="zone-repair",
                zone_name=ZONE_REPAIR,
                status=ZONE_STATUS_ACTIVE,
                allowed_step_types=["repair", "recovery"],
            ),
            ZONE_MUTATION: RuntimeZone(
                zone_id="zone-mutation",
                zone_name=ZONE_MUTATION,
                status=ZONE_STATUS_ACTIVE,
                allowed_step_types=["mutation", "apply_patch"],
            ),
            ZONE_SANDBOX: RuntimeZone(
                zone_id="zone-sandbox",
                zone_name=ZONE_SANDBOX,
                status=ZONE_STATUS_ACTIVE,
                allowed_step_types=["sandbox", "unsafe_tool"],
            ),
            ZONE_REPLAY: RuntimeZone(
                zone_id="zone-replay",
                zone_name=ZONE_REPLAY,
                status=ZONE_STATUS_ACTIVE,
                allowed_step_types=["replay", "reconstruction"],
            ),
        }

    def isolate_zone(self, zone_name: str) -> None:
        if zone_name in self.zones:
            zone = self.zones[zone_name]
            self.zones[zone_name] = RuntimeZone(
                zone_id=zone.zone_id,
                zone_name=zone.zone_name,
                status=ZONE_STATUS_ISOLATED,
                allowed_step_types=zone.allowed_step_types,
                isolated=True,
            )

    def route_step(
        self,
        *,
        step: dict[str, Any],
    ) -> RuntimeZoneRoutingDecision:
        step_type = str(step.get("type") or "").strip().lower()

        for zone_name, zone in self.zones.items():
            if step_type in zone.allowed_step_types:
                if zone.isolated:
                    return RuntimeZoneRoutingDecision(
                        route_status=ROUTE_BLOCKED,
                        selected_zone=zone_name,
                        execution_allowed=False,
                        reason="target_zone_isolated",
                        runtime_zones=[item.to_dict() for item in self.zones.values()],
                    )

                return RuntimeZoneRoutingDecision(
                    route_status=ROUTE_ALLOWED,
                    selected_zone=zone_name,
                    execution_allowed=True,
                    reason="zone_route_allowed",
                    runtime_zones=[item.to_dict() for item in self.zones.values()],
                )

        return RuntimeZoneRoutingDecision(
            route_status=ROUTE_REDIRECTED,
            selected_zone=ZONE_SANDBOX,
            execution_allowed=True,
            reason="unknown_step_redirected_to_sandbox",
            runtime_zones=[item.to_dict() for item in self.zones.values()],
        )


__all__ = [
    "RuntimeMultiZoneArchitecture",
    "RuntimeZone",
    "RuntimeZoneRoutingDecision",
    "ZONE_MAIN",
    "ZONE_REPAIR",
    "ZONE_MUTATION",
    "ZONE_SANDBOX",
    "ZONE_REPLAY",
    "ZONE_STATUS_ACTIVE",
    "ZONE_STATUS_ISOLATED",
    "ZONE_STATUS_DEGRADED",
    "ROUTE_ALLOWED",
    "ROUTE_REDIRECTED",
    "ROUTE_BLOCKED",
]
