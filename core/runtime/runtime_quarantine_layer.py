from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


QUARANTINE_STATUS_ACTIVE = "active"
QUARANTINE_STATUS_RELEASED = "released"
QUARANTINE_STATUS_ESCALATED = "escalated"

TARGET_TOOL = "tool"
TARGET_MUTATION = "mutation"
TARGET_BRANCH = "execution_branch"

ACTION_QUARANTINE = "quarantine"
ACTION_SANDBOX_ONLY = "sandbox_only"
ACTION_REQUIRE_APPROVAL = "require_approval"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def future_timestamp(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeQuarantineRecord:
    quarantine_id: str
    target_type: str
    target_name: str
    reason: str
    action: str
    status: str
    expires_at: str
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarantine_id": self.quarantine_id,
            "target_type": self.target_type,
            "target_name": self.target_name,
            "reason": self.reason,
            "action": self.action,
            "status": self.status,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeQuarantineDecision:
    quarantined: bool
    execution_allowed: bool
    enforcement_action: str
    quarantine_records: list[dict[str, Any]]
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
            "artifact_type": "runtime_quarantine_decision",
            "quarantined": self.quarantined,
            "execution_allowed": self.execution_allowed,
            "enforcement_action": self.enforcement_action,
            "quarantine_records": copy.deepcopy(self.quarantine_records),
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


class RuntimeQuarantineLayer:
    """
    Fault containment runtime layer.

    Isolates unstable tools/mutations/branches instead of allowing
    runtime-wide corruption spread.
    """

    def __init__(self) -> None:
        self.records: list[RuntimeQuarantineRecord] = []

    def quarantine_target(
        self,
        *,
        target_type: str,
        target_name: str,
        reason: str,
        severity: str,
    ) -> RuntimeQuarantineDecision:
        action = ACTION_REQUIRE_APPROVAL
        execution_allowed = True

        if severity == "critical":
            action = ACTION_QUARANTINE
            execution_allowed = False

        elif severity == "high":
            action = ACTION_SANDBOX_ONLY
            execution_allowed = True

        record = RuntimeQuarantineRecord(
            quarantine_id="quarantine-" + _stable_fingerprint(
                {
                    "target_type": target_type,
                    "target_name": target_name,
                    "reason": reason,
                }
            )[:16],
            target_type=target_type,
            target_name=target_name,
            reason=reason,
            action=action,
            status=QUARANTINE_STATUS_ACTIVE,
            expires_at=future_timestamp(60),
        )

        self.records.append(record)

        return RuntimeQuarantineDecision(
            quarantined=True,
            execution_allowed=execution_allowed,
            enforcement_action=action,
            quarantine_records=[item.to_dict() for item in self.records],
        )

    def is_quarantined(
        self,
        *,
        target_type: str,
        target_name: str,
    ) -> bool:
        for record in self.records:
            if (
                record.target_type == target_type
                and record.target_name == target_name
                and record.status == QUARANTINE_STATUS_ACTIVE
            ):
                return True
        return False

    def release_quarantine(
        self,
        *,
        quarantine_id: str,
    ) -> RuntimeQuarantineDecision:
        updated: list[RuntimeQuarantineRecord] = []

        for record in self.records:
            if record.quarantine_id == quarantine_id:
                updated.append(
                    RuntimeQuarantineRecord(
                        quarantine_id=record.quarantine_id,
                        target_type=record.target_type,
                        target_name=record.target_name,
                        reason=record.reason,
                        action=record.action,
                        status=QUARANTINE_STATUS_RELEASED,
                        expires_at=record.expires_at,
                        created_at=record.created_at,
                    )
                )
            else:
                updated.append(record)

        self.records = updated

        return RuntimeQuarantineDecision(
            quarantined=False,
            execution_allowed=True,
            enforcement_action="released",
            quarantine_records=[item.to_dict() for item in self.records],
        )


__all__ = [
    "RuntimeQuarantineLayer",
    "RuntimeQuarantineDecision",
    "RuntimeQuarantineRecord",
    "QUARANTINE_STATUS_ACTIVE",
    "QUARANTINE_STATUS_RELEASED",
    "QUARANTINE_STATUS_ESCALATED",
    "TARGET_TOOL",
    "TARGET_MUTATION",
    "TARGET_BRANCH",
    "ACTION_QUARANTINE",
    "ACTION_SANDBOX_ONLY",
    "ACTION_REQUIRE_APPROVAL",
]
