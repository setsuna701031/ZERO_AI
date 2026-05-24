"""Runtime identity and authority contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.runtime.runtime_closure import build_runtime_closure_fields


IDENTITY_TYPES = frozenset(
    {
        "HUMAN",
        "PLANNER",
        "REPAIR_LOOP",
        "REPLAY_ENGINE",
        "SELF_EDIT",
        "EXTERNAL_CONNECTOR",
        "PERSONA",
        "SYSTEM",
    }
)

AUTHORITY_DECISION_STATES = frozenset(
    {
        "allowed",
        "blocked",
        "restricted",
        "requires_confirmation",
        "sandbox_only",
    }
)

RISK_ORDER = {
    "LOW": 0,
    "MODERATE": 1,
    "HIGH": 2,
    "IRREVERSIBLE": 3,
    "EXTERNAL": 4,
}

AUTHORITY_DENIED_STATUSES = {
    "denied",
    "blocked",
    "rejected",
    "restricted",
    "requires_confirmation",
    "missing_ownership",
    "mismatch",
    "duplicate",
    "closed_transaction_boundary",
    "closed_authority_boundary",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_authority_metadata(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    nested = data.get("authority_seal")
    if isinstance(nested, Mapping):
        data = {**dict(nested), **data}

    authority_source = (
        _text(data.get("authority_source"))
        or _text(data.get("runtime_authority_source"))
        or _text(data.get("source"))
        or "legacy_runtime_authority"
    )
    authority_scope = (
        _text(data.get("authority_scope"))
        or _text(data.get("authority_scope_id"))
        or _text(data.get("scope_id"))
        or "legacy"
    )
    ownership_source = (
        _text(data.get("ownership_source"))
        or _text(data.get("canonical_owner"))
        or _text(data.get("owner"))
    )
    ownership_scope = (
        _text(data.get("ownership_scope"))
        or _text(data.get("capability_scope_id"))
        or _text(data.get("ownership_scope_id"))
    )
    explicit_status = _text(data.get("authority_status") or data.get("authority_state")).lower()
    reason = _text(data.get("authority_reason") or data.get("reason"))
    duplicate = isinstance(data.get("runtime_authority"), Mapping)
    transaction_boundary = data.get("transaction_boundary")
    tx_status = ""
    if isinstance(transaction_boundary, Mapping):
        tx_status = _text(transaction_boundary.get("transaction_status")).lower()
    closed_boundary = tx_status in {"committed", "rolled_back", "denied", "failed"}
    closure_status = _text(data.get("authority_closure_status") or data.get("closure_status")).lower()
    authority_closed = closure_status in {"closed", "sealed"} or bool(data.get("authority_immutable_state"))
    authority_signal_present = any(
        key in data
        for key in (
            "authority_source",
            "runtime_authority_source",
            "authority_scope",
            "authority_scope_id",
            "authority_status",
            "authority_state",
            "ownership_source",
            "ownership_scope",
            "canonical_owner",
            "owner",
        )
    )

    expected_owner = _text(data.get("expected_ownership_source"))
    mismatch = bool(expected_owner and ownership_source and expected_owner != ownership_source)

    if duplicate:
        status = "duplicate"
        reason = reason or "duplicate_authority_propagation"
    elif authority_closed and explicit_status in {"", "allowed", "opened", "active"}:
        status = "closed_authority_boundary"
        reason = reason or "closed_authority_boundary_cannot_reacquire_authority"
    elif closed_boundary and explicit_status in {"", "allowed", "opened", "active"}:
        status = "closed_transaction_boundary"
        reason = reason or "closed_transaction_boundary_cannot_reacquire_authority"
    elif explicit_status in AUTHORITY_DENIED_STATUSES:
        status = explicit_status
        reason = reason or f"authority_{explicit_status}"
    elif mismatch:
        status = "mismatch"
        reason = reason or "authority_ownership_mismatch"
    elif authority_signal_present and not ownership_source:
        status = "missing_ownership"
        reason = reason or "ownership_source_missing"
    else:
        status = explicit_status or "allowed"
        reason = reason or "authority_ownership_allowed"

    metadata = {
        "authority_source": authority_source,
        "authority_scope": authority_scope,
        "authority_status": status,
        "authority_reason": reason,
        "ownership_source": ownership_source or "legacy_runtime_ownership",
        "ownership_scope": ownership_scope or authority_scope,
    }
    if duplicate:
        nested_authority = data.get("runtime_authority") if isinstance(data.get("runtime_authority"), Mapping) else {}
        metadata["duplicate_authority_propagation"] = True
        metadata["duplicate_authority_evidence"] = {
            "authority_source": _text(nested_authority.get("authority_source")),
            "authority_scope": _text(nested_authority.get("authority_scope")),
            "authority_status": _text(nested_authority.get("authority_status")),
            "ownership_source": _text(nested_authority.get("ownership_source")),
            "ownership_scope": _text(nested_authority.get("ownership_scope")),
        }
    if mismatch:
        metadata["authority_mismatch_evidence"] = {
            "expected_ownership_source": expected_owner,
            "actual_ownership_source": ownership_source,
        }
    if closed_boundary:
        metadata["closed_transaction_boundary"] = True
        metadata["transaction_boundary"] = dict(transaction_boundary)
    closure = build_runtime_closure_fields(
        {
            **data,
            **metadata,
            "allow_existing_closure": True,
            "source": authority_source,
        },
        artifact_type="authority",
        artifact_id=authority_scope,
        finalized_by=authority_source,
    )
    if status == "closed_authority_boundary":
        closure["closure_evidence"].setdefault("mismatch_evidence", []).append(
            {"kind": "authority_reacquire_attempt", "authority_scope": authority_scope}
        )
    metadata.update(closure)
    return metadata


def authority_allows_execution(metadata: Mapping[str, Any] | None = None) -> bool:
    authority = build_authority_metadata(metadata)
    return _text(authority.get("authority_status")).lower() not in AUTHORITY_DENIED_STATUSES


@dataclass(frozen=True)
class RuntimeIdentity:
    identity_id: str
    identity_type: str
    source: str
    display_name: str
    lineage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeAuthorityScope:
    scope_id: str
    allowed_execution_types: tuple[str, ...] = ()
    allowed_mutation_types: tuple[str, ...] = ()
    allowed_paths: tuple[str, ...] = ()
    blocked_paths: tuple[str, ...] = ()
    risk_ceiling: str = "LOW"
    requires_confirmation: bool = False
    sandbox_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeAuthorityDecision:
    state: str
    reason: str
    identity: RuntimeIdentity
    authority_scope: RuntimeAuthorityScope
    risk_level: str
    target_path: str | None = None
    lineage: dict[str, Any] = field(default_factory=dict)
    audit_tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.state in {"allowed", "sandbox_only"}


@dataclass(frozen=True)
class RuntimeAuthorityResult:
    decision: RuntimeAuthorityDecision
    evaluated: bool = True

    @property
    def allowed(self) -> bool:
        return self.decision.allowed

    @property
    def state(self) -> str:
        return self.decision.state

    def to_metadata(self) -> dict[str, Any]:
        return {
            "authority_evaluated": self.evaluated,
            "authority_state": self.decision.state,
            "authority_reason": self.decision.reason,
            "runtime_identity": {
                "identity_id": self.decision.identity.identity_id,
                "identity_type": self.decision.identity.identity_type,
                "source": self.decision.identity.source,
                "display_name": self.decision.identity.display_name,
                "lineage": dict(self.decision.identity.lineage),
                "metadata": dict(self.decision.identity.metadata),
            },
            "authority_scope": {
                "scope_id": self.decision.authority_scope.scope_id,
                "risk_ceiling": self.decision.authority_scope.risk_ceiling,
                "requires_confirmation": self.decision.authority_scope.requires_confirmation,
                "sandbox_only": self.decision.authority_scope.sandbox_only,
            },
            "authority_lineage": dict(self.decision.lineage),
            "authority_audit_tags": list(self.decision.audit_tags),
            "authority_metadata": dict(self.decision.metadata),
        }


class RuntimeAuthorityEvaluator:
    def evaluate(
        self,
        *,
        identity: RuntimeIdentity,
        authority_scope: RuntimeAuthorityScope,
        execution_type: str | None = None,
        mutation_type: str | None = None,
        target_path: str | Path | None = None,
        risk_level: str = "LOW",
        lineage: Mapping[str, Any] | None = None,
    ) -> RuntimeAuthorityResult:
        identity_type = str(identity.identity_type or "").strip().upper()
        target_text = str(target_path) if target_path is not None else None
        lineage_dict = {**dict(identity.lineage), **dict(lineage or {})}
        audit_tags = (
            "authority",
            f"identity:{identity_type}",
            f"risk:{risk_level}",
        )

        if identity_type not in IDENTITY_TYPES:
            return self._result(
                state="blocked",
                reason="unsupported_identity_type",
                identity=identity,
                authority_scope=authority_scope,
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
            )

        if mutation_type and not _contains_or_wildcard(
            authority_scope.allowed_mutation_types,
            mutation_type,
        ):
            return self._result(
                state="restricted",
                reason="mutation_type_outside_authority_scope",
                identity=identity,
                authority_scope=authority_scope,
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
            )

        if execution_type and not _contains_or_wildcard(
            authority_scope.allowed_execution_types,
            execution_type,
        ):
            return self._result(
                state="restricted",
                reason="execution_type_outside_authority_scope",
                identity=identity,
                authority_scope=authority_scope,
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
            )

        if target_text and _path_matches_any(target_text, authority_scope.blocked_paths):
            return self._result(
                state="blocked",
                reason="target_path_blocked_by_authority_scope",
                identity=identity,
                authority_scope=authority_scope,
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
            )

        if target_text and authority_scope.allowed_paths and not _path_matches_any(
            target_text,
            authority_scope.allowed_paths,
        ):
            return self._result(
                state="restricted",
                reason="target_path_outside_authority_scope",
                identity=identity,
                authority_scope=authority_scope,
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
            )

        if _risk_value(risk_level) > _risk_value(authority_scope.risk_ceiling):
            return self._result(
                state="requires_confirmation",
                reason="risk_exceeds_authority_ceiling",
                identity=identity,
                authority_scope=authority_scope,
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
            )

        if authority_scope.requires_confirmation:
            return self._result(
                state="requires_confirmation",
                reason="authority_scope_requires_confirmation",
                identity=identity,
                authority_scope=authority_scope,
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
            )

        if authority_scope.sandbox_only:
            return self._result(
                state="sandbox_only",
                reason="authority_scope_sandbox_only",
                identity=identity,
                authority_scope=authority_scope,
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
            )

        return self._result(
            state="allowed",
            reason="authority_scope_allows_request",
            identity=identity,
            authority_scope=authority_scope,
            risk_level=risk_level,
            target_path=target_text,
            lineage=lineage_dict,
            audit_tags=audit_tags,
        )

    def _result(
        self,
        *,
        state: str,
        reason: str,
        identity: RuntimeIdentity,
        authority_scope: RuntimeAuthorityScope,
        risk_level: str,
        target_path: str | None,
        lineage: Mapping[str, Any],
        audit_tags: tuple[str, ...],
    ) -> RuntimeAuthorityResult:
        return RuntimeAuthorityResult(
            decision=RuntimeAuthorityDecision(
                state=state if state in AUTHORITY_DECISION_STATES else "blocked",
                reason=reason,
                identity=identity,
                authority_scope=authority_scope,
                risk_level=risk_level,
                target_path=target_path,
                lineage=dict(lineage),
                audit_tags=tuple(audit_tags),
                metadata={
                    "target_path": target_path,
                    "risk_level": risk_level,
                },
            )
        )


def default_human_authority_scope() -> RuntimeAuthorityScope:
    return RuntimeAuthorityScope(
        scope_id="authority:human:workspace",
        allowed_execution_types=("*",),
        allowed_mutation_types=("*",),
        allowed_paths=("*",),
        blocked_paths=(),
        risk_ceiling="IRREVERSIBLE",
    )


def _contains_or_wildcard(values: Iterable[str], item: str) -> bool:
    normalized = {str(value).strip().lower() for value in values}
    return "*" in normalized or str(item).strip().lower() in normalized


def _path_matches_any(path: str, patterns: Iterable[str]) -> bool:
    normalized_path = path.replace("\\", "/").lower()
    for pattern in patterns:
        text = str(pattern).replace("\\", "/").lower()
        if text == "*":
            return True
        if text and text in normalized_path:
            return True
    return False


def _risk_value(risk_level: str) -> int:
    return RISK_ORDER.get(str(risk_level or "LOW").upper(), RISK_ORDER["HIGH"])
