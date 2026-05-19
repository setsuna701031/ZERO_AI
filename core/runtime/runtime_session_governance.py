"""Runtime session governance contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from core.runtime.runtime_authority import RuntimeAuthorityScope, RuntimeIdentity


SESSION_LIFECYCLE_STATES = frozenset(
    {
        "created",
        "active",
        "suspended",
        "sealed",
        "rolled_back",
        "failed",
        "expired",
    }
)


@dataclass(frozen=True)
class RuntimeSession:
    session_id: str
    owner_identity: RuntimeIdentity
    authority_scope: RuntimeAuthorityScope
    started_at: str
    ended_at: str | None
    lineage: dict[str, Any]
    active_execution_ids: tuple[str, ...] = ()
    active_transaction_ids: tuple[str, ...] = ()
    active_replay_ids: tuple[str, ...] = ()
    status: str = "created"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeSessionPolicy:
    policy_id: str
    allowed_owner_id: str
    allow_replay: bool = True
    allow_rollback: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeSessionDecision:
    state: str
    reason: str
    session_id: str
    owner_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.state in {"allowed", "active"}


@dataclass(frozen=True)
class RuntimeSessionResult:
    session: RuntimeSession
    decision: RuntimeSessionDecision
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision.allowed


class RuntimeSessionGovernance:
    def create_session(
        self,
        *,
        session_id: str,
        owner_identity: RuntimeIdentity,
        authority_scope: RuntimeAuthorityScope,
        lineage: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSessionResult:
        now = _utc_timestamp()
        session = RuntimeSession(
            session_id=session_id,
            owner_identity=owner_identity,
            authority_scope=authority_scope,
            started_at=now,
            ended_at=None,
            lineage=dict(lineage),
            status="created",
            metadata=dict(metadata or {}),
        )
        return RuntimeSessionResult(
            session=session,
            decision=RuntimeSessionDecision(
                state="allowed",
                reason="session_created",
                session_id=session_id,
                owner_id=owner_identity.identity_id,
            ),
            metadata={"session_lifecycle": ("created",)},
        )

    def transition(
        self,
        *,
        session: RuntimeSession,
        status: str,
        actor_identity: RuntimeIdentity,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSessionResult:
        if status not in SESSION_LIFECYCLE_STATES:
            return RuntimeSessionResult(
                session=session,
                decision=RuntimeSessionDecision(
                    state="blocked",
                    reason="unsupported_session_state",
                    session_id=session.session_id,
                    owner_id=session.owner_identity.identity_id,
                ),
                metadata=dict(metadata or {}),
            )
        if actor_identity.identity_id != session.owner_identity.identity_id:
            return RuntimeSessionResult(
                session=session,
                decision=RuntimeSessionDecision(
                    state="blocked",
                    reason="session_owner_mismatch",
                    session_id=session.session_id,
                    owner_id=session.owner_identity.identity_id,
                ),
                metadata=dict(metadata or {}),
            )
        ended_at = _utc_timestamp() if status in {"sealed", "rolled_back", "failed", "expired"} else None
        updated = replace(session, status=status, ended_at=ended_at)
        return RuntimeSessionResult(
            session=updated,
            decision=RuntimeSessionDecision(
                state="active" if status == "active" else "allowed",
                reason=f"session_{status}",
                session_id=session.session_id,
                owner_id=session.owner_identity.identity_id,
            ),
            metadata={"session_lifecycle": (session.status, status), **dict(metadata or {})},
        )


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
