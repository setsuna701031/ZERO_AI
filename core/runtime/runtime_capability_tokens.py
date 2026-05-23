from __future__ import annotations

import copy
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


TOKEN_ACTIVE = "active"
TOKEN_REVOKED = "revoked"
TOKEN_EXPIRED = "expired"

CAP_MUTATION = "mutation"
CAP_REPAIR = "repair"
CAP_AUTHORITY = "authority"
CAP_SANDBOX = "sandbox"
CAP_REPLAY = "replay"

ZONE_MUTATION = "mutation_runtime"
ZONE_REPAIR = "repair_runtime"
ZONE_AUTHORITY = "authority_runtime"
ZONE_SANDBOX = "sandbox_runtime"
ZONE_REPLAY = "replay_runtime"

ACCESS_ALLOWED = "allowed"
ACCESS_DENIED = "denied"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_timestamp() -> str:
    return utc_now().isoformat()


def future_timestamp(minutes: int) -> str:
    return (utc_now() + timedelta(minutes=minutes)).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeCapabilityToken:
    token_id: str
    capability: str
    zone: str
    status: str
    issued_at: str
    expires_at: str
    revoked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "capability": self.capability,
            "zone": self.zone,
            "status": self.status,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revoked_reason": self.revoked_reason,
        }


@dataclass(frozen=True)
class RuntimeCapabilityDecision:
    access_status: str
    allowed: bool
    reason: str
    token: dict[str, Any]
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
            "artifact_type": "runtime_capability_decision",
            "access_status": self.access_status,
            "allowed": self.allowed,
            "reason": self.reason,
            "token": copy.deepcopy(self.token),
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


class RuntimeCapabilityTokenManager:
    """
    Capability-based runtime authority manager.

    Runtime zones must possess valid capability tokens before accessing
    privileged runtime operations.
    """

    def __init__(self) -> None:
        self.tokens: dict[str, RuntimeCapabilityToken] = {}

    def issue_token(
        self,
        *,
        capability: str,
        zone: str,
        expires_in_minutes: int = 60,
    ) -> RuntimeCapabilityToken:
        token = RuntimeCapabilityToken(
            token_id="token-" + secrets.token_hex(8),
            capability=str(capability),
            zone=str(zone),
            status=TOKEN_ACTIVE,
            issued_at=utc_timestamp(),
            expires_at=future_timestamp(expires_in_minutes),
        )

        self.tokens[token.token_id] = token
        return token

    def revoke_token(
        self,
        *,
        token_id: str,
        reason: str,
    ) -> RuntimeCapabilityToken:
        token = self.tokens[token_id]

        revoked = RuntimeCapabilityToken(
            token_id=token.token_id,
            capability=token.capability,
            zone=token.zone,
            status=TOKEN_REVOKED,
            issued_at=token.issued_at,
            expires_at=token.expires_at,
            revoked_reason=reason,
        )

        self.tokens[token_id] = revoked
        return revoked

    def validate_access(
        self,
        *,
        token_id: str,
        required_capability: str,
        target_zone: str,
    ) -> RuntimeCapabilityDecision:
        token = self.tokens.get(token_id)

        if token is None:
            return self._decision(
                allowed=False,
                status=ACCESS_DENIED,
                reason="token_not_found",
                token={},
            )

        now = utc_now()

        expires_at = datetime.fromisoformat(token.expires_at)

        if token.status == TOKEN_REVOKED:
            return self._decision(
                allowed=False,
                status=ACCESS_DENIED,
                reason="token_revoked",
                token=token.to_dict(),
            )

        if expires_at <= now:
            expired = RuntimeCapabilityToken(
                token_id=token.token_id,
                capability=token.capability,
                zone=token.zone,
                status=TOKEN_EXPIRED,
                issued_at=token.issued_at,
                expires_at=token.expires_at,
                revoked_reason=token.revoked_reason,
            )
            self.tokens[token_id] = expired

            return self._decision(
                allowed=False,
                status=ACCESS_DENIED,
                reason="token_expired",
                token=expired.to_dict(),
            )

        if token.capability != required_capability:
            return self._decision(
                allowed=False,
                status=ACCESS_DENIED,
                reason="capability_mismatch",
                token=token.to_dict(),
            )

        if token.zone != target_zone:
            return self._decision(
                allowed=False,
                status=ACCESS_DENIED,
                reason="zone_mismatch",
                token=token.to_dict(),
            )

        return self._decision(
            allowed=True,
            status=ACCESS_ALLOWED,
            reason="capability_access_allowed",
            token=token.to_dict(),
        )

    def _decision(
        self,
        *,
        allowed: bool,
        status: str,
        reason: str,
        token: dict[str, Any],
    ) -> RuntimeCapabilityDecision:
        return RuntimeCapabilityDecision(
            access_status=status,
            allowed=allowed,
            reason=reason,
            token=copy.deepcopy(token),
        )


__all__ = [
    "RuntimeCapabilityTokenManager",
    "RuntimeCapabilityToken",
    "RuntimeCapabilityDecision",
    "TOKEN_ACTIVE",
    "TOKEN_REVOKED",
    "TOKEN_EXPIRED",
    "CAP_MUTATION",
    "CAP_REPAIR",
    "CAP_AUTHORITY",
    "CAP_SANDBOX",
    "CAP_REPLAY",
    "ZONE_MUTATION",
    "ZONE_REPAIR",
    "ZONE_AUTHORITY",
    "ZONE_SANDBOX",
    "ZONE_REPLAY",
    "ACCESS_ALLOWED",
    "ACCESS_DENIED",
]
