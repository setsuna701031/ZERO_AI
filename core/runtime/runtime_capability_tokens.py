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
    authority_decision_id: str = ""
    scope: tuple[tuple[str, str], ...] = ()
    lineage: tuple[tuple[str, str], ...] = ()
    source: str = "legacy_token_manager"
    execution_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "capability": self.capability,
            "zone": self.zone,
            "status": self.status,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revoked_reason": self.revoked_reason,
            "authority_decision_id": self.authority_decision_id,
            "scope": dict(self.scope),
            "lineage": dict(self.lineage),
            "source": self.source,
            "execution_id": self.execution_id,
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
    Capability-token manager for runtime zones.

    This layer is not execution authority. It only issues and validates scoped
    bearer tokens that may be used as proof after an execution-authority policy
    decision has allowed the requested runtime operation.
    """

    def __init__(self) -> None:
        self.tokens: dict[str, RuntimeCapabilityToken] = {}
        self.authority_decisions_issued: set[str] = set()

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

    def issue_from_authority_decision(
        self,
        decision: Any,
        *,
        capability: str,
        zone: str,
        scope: dict[str, Any],
        lineage: dict[str, Any],
        expires_in_minutes: int = 60,
    ) -> RuntimeCapabilityToken:
        """Issue the sole token for one allowed authority decision."""
        decision_id = str(getattr(decision, "decision_id", "") or "").strip()
        if not bool(getattr(decision, "allowed", False)) or not decision_id:
            raise PermissionError("allowed_authority_decision_required")
        if decision_id in self.authority_decisions_issued:
            raise PermissionError("capability_reissue_forbidden")
        normalized_scope = tuple(sorted((str(key), str(value)) for key, value in scope.items()))
        normalized_lineage = tuple(sorted((str(key), str(value)) for key, value in lineage.items()))
        if not normalized_scope or not normalized_lineage or any(value == "*" for _, value in normalized_scope):
            raise PermissionError("explicit_capability_scope_and_lineage_required")
        execution_id = str(scope.get("execution_id") or lineage.get("execution_id") or "").strip()
        if not execution_id:
            raise PermissionError("capability_execution_identity_required")
        token_id = "token-" + _stable_fingerprint(
            {"decision_id": decision_id, "capability": capability, "zone": zone, "scope": normalized_scope, "lineage": normalized_lineage}
        )[:16]
        token = RuntimeCapabilityToken(
            token_id=token_id,
            capability=str(capability),
            zone=str(zone),
            status=TOKEN_ACTIVE,
            issued_at=utc_timestamp(),
            expires_at=future_timestamp(expires_in_minutes),
            authority_decision_id=decision_id,
            scope=normalized_scope,
            lineage=normalized_lineage,
            source="authority_decision",
            execution_id=execution_id,
        )
        self.tokens[token.token_id] = token
        self.authority_decisions_issued.add(decision_id)
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
            authority_decision_id=token.authority_decision_id,
            scope=token.scope,
            lineage=token.lineage,
            source=token.source,
            execution_id=token.execution_id,
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
                authority_decision_id=token.authority_decision_id,
                scope=token.scope,
                lineage=token.lineage,
                source=token.source,
                execution_id=token.execution_id,
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
