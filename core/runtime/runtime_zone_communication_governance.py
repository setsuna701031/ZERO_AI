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
ZONE_AUTHORITY = "authority_runtime"

CHANNEL_ALLOWED = "allowed"
CHANNEL_BLOCKED = "blocked"
CHANNEL_BRIDGED = "bridged"
CHANNEL_REVIEW_REQUIRED = "review_required"

BRIDGE_GOVERNED = "governed_bridge"
BRIDGE_READ_ONLY = "read_only_bridge"
BRIDGE_AUTHORITY = "authority_bridge"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeZoneMessage:
    source_zone: str
    target_zone: str
    message_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_zone": self.source_zone,
            "target_zone": self.target_zone,
            "message_type": self.message_type,
            "payload": copy.deepcopy(self.payload),
        }


@dataclass(frozen=True)
class RuntimeZoneCommunicationDecision:
    channel_status: str
    bridge: str
    allowed: bool
    reason: str
    message: dict[str, Any]
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
            "artifact_type": "runtime_zone_communication_decision",
            "channel_status": self.channel_status,
            "bridge": self.bridge,
            "allowed": self.allowed,
            "reason": self.reason,
            "message": copy.deepcopy(self.message),
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


class RuntimeZoneCommunicationGovernance:
    """
    Inter-zone communication governance.

    Prevents runtime zones from directly contaminating each other.
    Mutation/sandbox/repair zones must communicate through governed bridges.
    """

    def evaluate_message(
        self,
        *,
        source_zone: str,
        target_zone: str,
        message_type: str,
        payload: dict[str, Any] | None = None,
    ) -> RuntimeZoneCommunicationDecision:
        message = RuntimeZoneMessage(
            source_zone=str(source_zone or ""),
            target_zone=str(target_zone or ""),
            message_type=str(message_type or ""),
            payload=copy.deepcopy(payload or {}),
        ).to_dict()

        source = message["source_zone"]
        target = message["target_zone"]
        msg_type = message["message_type"]

        # Authority can write main runtime through authority bridge.
        if source == ZONE_AUTHORITY and target == ZONE_MAIN:
            return self._decision(
                status=CHANNEL_BRIDGED,
                bridge=BRIDGE_AUTHORITY,
                allowed=True,
                reason="authority_bridge_required",
                message=message,
            )

        # Replay can only read into main, not write.
        if source == ZONE_REPLAY and target == ZONE_MAIN:
            if msg_type in {"read_state", "replay_reference", "incident_summary"}:
                return self._decision(
                    status=CHANNEL_BRIDGED,
                    bridge=BRIDGE_READ_ONLY,
                    allowed=True,
                    reason="replay_read_only_bridge",
                    message=message,
                )
            return self._decision(
                status=CHANNEL_BLOCKED,
                bridge=BRIDGE_READ_ONLY,
                allowed=False,
                reason="replay_cannot_write_main_runtime",
                message=message,
            )

        # Mutation cannot directly write main runtime.
        if source == ZONE_MUTATION and target == ZONE_MAIN:
            return self._decision(
                status=CHANNEL_REVIEW_REQUIRED,
                bridge=BRIDGE_GOVERNED,
                allowed=False,
                reason="mutation_to_main_requires_governed_authority",
                message=message,
            )

        # Sandbox cannot touch authority directly.
        if source == ZONE_SANDBOX and target == ZONE_AUTHORITY:
            return self._decision(
                status=CHANNEL_BLOCKED,
                bridge=BRIDGE_GOVERNED,
                allowed=False,
                reason="sandbox_cannot_contact_authority",
                message=message,
            )

        # Repair runtime can request recovery through governed bridge.
        if source == ZONE_REPAIR and target in {ZONE_MAIN, ZONE_AUTHORITY}:
            return self._decision(
                status=CHANNEL_BRIDGED,
                bridge=BRIDGE_GOVERNED,
                allowed=True,
                reason="repair_governed_bridge",
                message=message,
            )

        # Same-zone communication is allowed.
        if source == target:
            return self._decision(
                status=CHANNEL_ALLOWED,
                bridge="local",
                allowed=True,
                reason="same_zone_communication",
                message=message,
            )

        return self._decision(
            status=CHANNEL_REVIEW_REQUIRED,
            bridge=BRIDGE_GOVERNED,
            allowed=False,
            reason="cross_zone_review_required",
            message=message,
        )

    def _decision(
        self,
        *,
        status: str,
        bridge: str,
        allowed: bool,
        reason: str,
        message: dict[str, Any],
    ) -> RuntimeZoneCommunicationDecision:
        return RuntimeZoneCommunicationDecision(
            channel_status=status,
            bridge=bridge,
            allowed=allowed,
            reason=reason,
            message=copy.deepcopy(message),
        )


def govern_zone_message(
    *,
    source_zone: str,
    target_zone: str,
    message_type: str,
    payload: dict[str, Any] | None = None,
) -> RuntimeZoneCommunicationDecision:
    runtime = RuntimeZoneCommunicationGovernance()
    return runtime.evaluate_message(
        source_zone=source_zone,
        target_zone=target_zone,
        message_type=message_type,
        payload=payload,
    )


__all__ = [
    "RuntimeZoneCommunicationGovernance",
    "RuntimeZoneCommunicationDecision",
    "RuntimeZoneMessage",
    "ZONE_MAIN",
    "ZONE_REPAIR",
    "ZONE_MUTATION",
    "ZONE_SANDBOX",
    "ZONE_REPLAY",
    "ZONE_AUTHORITY",
    "CHANNEL_ALLOWED",
    "CHANNEL_BLOCKED",
    "CHANNEL_BRIDGED",
    "CHANNEL_REVIEW_REQUIRED",
    "BRIDGE_GOVERNED",
    "BRIDGE_READ_ONLY",
    "BRIDGE_AUTHORITY",
    "govern_zone_message",
]
