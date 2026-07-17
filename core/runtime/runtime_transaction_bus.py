from __future__ import annotations

import copy
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


BUS_PENDING = "pending"
BUS_ROUTED = "routed"
BUS_BLOCKED = "blocked"
BUS_COMPLETED = "completed"

CHANNEL_MUTATION = "mutation_request"
CHANNEL_REPAIR = "repair_request"
CHANNEL_AUTHORITY = "authority_escalation"
CHANNEL_REPLAY = "replay_reconstruction"
CHANNEL_POLICY = "policy_transition"

ZONE_MAIN = "main_runtime"
ZONE_MUTATION = "mutation_runtime"
ZONE_REPAIR = "repair_runtime"
ZONE_AUTHORITY = "authority_runtime"
ZONE_REPLAY = "replay_runtime"

ROUTE_ALLOWED = "allowed"
ROUTE_REVIEW = "review_required"
ROUTE_BLOCKED = "blocked"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeTransaction:
    transaction_id: str
    source_zone: str
    target_zone: str
    channel: str
    payload: dict[str, Any]
    status: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "source_zone": self.source_zone,
            "target_zone": self.target_zone,
            "channel": self.channel,
            "payload": copy.deepcopy(self.payload),
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeTransactionDecision:
    route_status: str
    allowed: bool
    reason: str
    transaction: dict[str, Any]
    bus_snapshot: list[dict[str, Any]]
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
            "artifact_type": "runtime_transaction_decision",
            "route_status": self.route_status,
            "allowed": self.allowed,
            "reason": self.reason,
            "transaction": copy.deepcopy(self.transaction),
            "bus_snapshot": copy.deepcopy(self.bus_snapshot),
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


class RuntimeTransactionBus:
    """
    Governed runtime transaction bus.

    Runtime zones communicate through audited transactions instead of
    direct execution calls.
    """

    def __init__(self) -> None:
        self.transactions: list[RuntimeTransaction] = []

    def submit_transaction(
        self,
        *,
        source_zone: str,
        target_zone: str,
        channel: str,
        payload: dict[str, Any] | None = None,
    ) -> RuntimeTransactionDecision:
        payload_data = copy.deepcopy(payload or {})

        transaction = RuntimeTransaction(
            transaction_id="tx-" + secrets.token_hex(8),
            source_zone=str(source_zone),
            target_zone=str(target_zone),
            channel=str(channel),
            payload=payload_data,
            status=BUS_PENDING,
            created_at=utc_timestamp(),
        )

        decision = self._govern_transaction(transaction)

        updated = RuntimeTransaction(
            transaction_id=transaction.transaction_id,
            source_zone=transaction.source_zone,
            target_zone=transaction.target_zone,
            channel=transaction.channel,
            payload=transaction.payload,
            status=decision["status"],
            created_at=transaction.created_at,
        )

        self.transactions.append(updated)

        return RuntimeTransactionDecision(
            route_status=decision["route_status"],
            allowed=decision["allowed"],
            reason=decision["reason"],
            transaction=updated.to_dict(),
            bus_snapshot=[item.to_dict() for item in self.transactions],
        )

    def _govern_transaction(
        self,
        transaction: RuntimeTransaction,
    ) -> dict[str, Any]:
        source = transaction.source_zone
        target = transaction.target_zone
        channel = transaction.channel

        # Mutation to main always requires review.
        if (
            source == ZONE_MUTATION
            and target == ZONE_MAIN
            and channel == CHANNEL_MUTATION
        ):
            return {
                "route_status": ROUTE_REVIEW,
                "allowed": False,
                "reason": "mutation_transaction_requires_review",
                "status": BUS_BLOCKED,
            }

        # Repair to authority allowed.
        if (
            source == ZONE_REPAIR
            and target == ZONE_AUTHORITY
            and channel == CHANNEL_REPAIR
        ):
            return {
                "route_status": ROUTE_ALLOWED,
                "allowed": True,
                "reason": "repair_transaction_allowed",
                "status": BUS_ROUTED,
            }

        # Replay reconstruction allowed read-only.
        if (
            source == ZONE_REPLAY
            and target == ZONE_MAIN
            and channel == CHANNEL_REPLAY
        ):
            return {
                "route_status": ROUTE_ALLOWED,
                "allowed": True,
                "reason": "replay_reconstruction_allowed",
                "status": BUS_ROUTED,
            }

        # Authority escalation allowed.
        if (
            source == ZONE_MAIN
            and target == ZONE_AUTHORITY
            and channel == CHANNEL_AUTHORITY
        ):
            return {
                "route_status": ROUTE_ALLOWED,
                "allowed": True,
                "reason": "authority_escalation_allowed",
                "status": BUS_ROUTED,
            }

        # Unknown cross-zone traffic blocked.
        return {
            "route_status": ROUTE_BLOCKED,
            "allowed": False,
            "reason": "transaction_route_blocked",
            "status": BUS_BLOCKED,
        }


__all__ = [
    "RuntimeTransactionBus",
    "RuntimeTransaction",
    "RuntimeTransactionDecision",
    "BUS_PENDING",
    "BUS_ROUTED",
    "BUS_BLOCKED",
    "BUS_COMPLETED",
    "CHANNEL_MUTATION",
    "CHANNEL_REPAIR",
    "CHANNEL_AUTHORITY",
    "CHANNEL_REPLAY",
    "CHANNEL_POLICY",
    "ZONE_MAIN",
    "ZONE_MUTATION",
    "ZONE_REPAIR",
    "ZONE_AUTHORITY",
    "ZONE_REPLAY",
    "ROUTE_ALLOWED",
    "ROUTE_REVIEW",
    "ROUTE_BLOCKED",
]
