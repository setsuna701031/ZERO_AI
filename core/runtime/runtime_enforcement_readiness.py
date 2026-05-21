from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.runtime.runtime_status import normalize_runtime_status
from core.runtime.runtime_status_transition import (
    can_transition_runtime_status,
    is_runtime_status_regression,
    validate_runtime_status_transition,
)


READINESS_SAFE_TO_ENFORCE = "safe_to_enforce"
READINESS_OBSERVE_ONLY = "observe_only"
READINESS_REVIEW_REQUIRED = "review_required"
READINESS_BLOCK_RECOMMENDED = "block_recommended"


class RuntimeEnforcementMode(StrEnum):
    AUDIT_ONLY = "audit_only"
    DRY_RUN = "dry_run"
    ENFORCE = "enforce"


class RuntimeTransitionBlockedError(RuntimeError):
    def __init__(self, decision: "RuntimeEnforcementDecision") -> None:
        self.decision = decision
        super().__init__(decision.reason)


@dataclass(frozen=True)
class RuntimeEnforcementDecision:
    allowed: bool
    blocked: bool
    would_block: bool
    mode: str
    classification: str
    safe_to_enforce: bool
    reason: str
    evidence_required: bool
    evidence_present: bool
    source_status: str
    target_status: str
    transition: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blocked": self.blocked,
            "would_block": self.would_block,
            "mode": self.mode,
            "classification": self.classification,
            "safe_to_enforce": self.safe_to_enforce,
            "reason": self.reason,
            "evidence_required": self.evidence_required,
            "evidence_present": self.evidence_present,
            "source_status": self.source_status,
            "target_status": self.target_status,
            "transition": copy.deepcopy(self.transition),
            "metadata": copy.deepcopy(self.metadata),
        }


def runtime_enforcement_decision_snapshot(decision: Any) -> dict[str, Any]:
    """Return a stable, persistence-safe enforcement decision snapshot.

    The runtime lifecycle layer stores this shape in transition records so replay,
    audit, and recovery reconstruction can read enforcement history without
    depending on live RuntimeEnforcementDecision objects.
    """

    if isinstance(decision, RuntimeEnforcementDecision):
        payload = decision.to_dict()
    elif isinstance(decision, dict):
        payload = copy.deepcopy(decision)
    else:
        payload = {}

    transition = payload.get("transition")
    if not isinstance(transition, dict):
        transition = {}

    return {
        "schema": "runtime_enforcement_decision.v1",
        "allowed": bool(payload.get("allowed", True)),
        "blocked": bool(payload.get("blocked", False)),
        "would_block": bool(payload.get("would_block", False)),
        "mode": normalize_runtime_enforcement_mode(payload.get("mode")),
        "classification": str(payload.get("classification") or ""),
        "safe_to_enforce": bool(payload.get("safe_to_enforce", False)),
        "reason": str(payload.get("reason") or ""),
        "evidence_required": bool(payload.get("evidence_required", False)),
        "evidence_present": bool(payload.get("evidence_present", False)),
        "source_status": str(payload.get("source_status") or transition.get("from_status") or ""),
        "target_status": str(payload.get("target_status") or transition.get("to_status") or ""),
        "transition": copy.deepcopy(transition),
        "metadata": copy.deepcopy(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
    }


_HARD_BLOCK_TRANSITIONS = {
    ("verified", "running"),
    ("failed", "verifying"),
    ("blocked", "executed"),
    ("rolled_back", "committed"),
    ("replayed", "queued"),
}

_OBSERVE_ONLY_TRANSITIONS = {
    ("running", "committed"),
    ("unknown", "recovered"),
    ("unknown", "replayed"),
    ("executed", "sealed"),
    ("recovered", "sealed"),
}

_RECOVERY_REPLAY_STATUSES = {
    "recovering",
    "recovered",
    "replaying",
    "replayed",
}


def classify_runtime_transition_enforcement(
    from_status: Any,
    to_status: Any,
    *,
    transition_allowed: bool | None = None,
    transition_regression: bool | None = None,
    transition_evidence: dict[str, Any] | None = None,
    source: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del metadata
    source_status = normalize_runtime_status(from_status)
    target_status = normalize_runtime_status(to_status)
    validation = validate_runtime_status_transition(source_status, target_status)
    allowed = bool(validation["allowed"] if transition_allowed is None else transition_allowed)
    regression = bool(
        is_runtime_status_regression(source_status, target_status)
        if transition_regression is None
        else transition_regression
    )
    evidence_present = isinstance(transition_evidence, dict) and bool(transition_evidence)
    source_present = bool(str(source or "").strip())

    classification = READINESS_REVIEW_REQUIRED
    reason = "transition requires review"

    if source_status == "sealed" and target_status != "sealed":
        classification = READINESS_BLOCK_RECOMMENDED
        reason = "sealed state is terminal"
    elif (source_status, target_status) in _HARD_BLOCK_TRANSITIONS:
        classification = READINESS_BLOCK_RECOMMENDED
        reason = "canonical regression"
    elif not evidence_present:
        classification = READINESS_REVIEW_REQUIRED
        reason = "transition evidence missing"
    elif not source_present:
        classification = READINESS_REVIEW_REQUIRED
        reason = "transition source missing"
    elif (
        source_status in _RECOVERY_REPLAY_STATUSES
        or target_status in _RECOVERY_REPLAY_STATUSES
    ) and not evidence_present:
        classification = READINESS_REVIEW_REQUIRED
        reason = "recovery/replay transition evidence missing"
    elif not allowed and regression:
        classification = READINESS_REVIEW_REQUIRED
        reason = "transition is outside canonical graph"
    elif (source_status, target_status) in _OBSERVE_ONLY_TRANSITIONS:
        classification = READINESS_OBSERVE_ONLY
        reason = "legacy shortcut or historical runtime path"
    elif can_transition_runtime_status(source_status, target_status):
        classification = READINESS_OBSERVE_ONLY
        reason = "allowed transition observed; hard enforcement not enabled"

    safe_to_enforce = classification == READINESS_BLOCK_RECOMMENDED
    review_required = classification == READINESS_REVIEW_REQUIRED
    block_recommended = classification == READINESS_BLOCK_RECOMMENDED
    observe_only = classification == READINESS_OBSERVE_ONLY

    return {
        "from_status": source_status,
        "to_status": target_status,
        "allowed": allowed,
        "regression": regression,
        "enforcement_readiness": classification,
        "enforcement_classification": classification,
        "enforcement_reason": reason,
        "safe_to_enforce": bool(safe_to_enforce),
        "review_required": bool(review_required),
        "block_recommended": bool(block_recommended),
        "observe_only": bool(observe_only),
    }


def runtime_enforcement_readiness_payload(
    transition_payload: Any,
    *,
    source: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = copy.deepcopy(transition_payload) if isinstance(transition_payload, dict) else {}
    classification = classify_runtime_transition_enforcement(
        payload.get("from_status"),
        payload.get("to_status"),
        transition_allowed=payload.get("allowed"),
        transition_regression=payload.get("regression"),
        transition_evidence=payload.get("transition_evidence"),
        source=source or payload.get("transition_source") or payload.get("source") or "",
        metadata=metadata if metadata is not None else payload.get("metadata"),
    )
    return {
        **payload,
        **classification,
    }


def normalize_runtime_enforcement_mode(mode: Any = None) -> str:
    if isinstance(mode, RuntimeEnforcementMode):
        return mode.value
    value = str(mode or RuntimeEnforcementMode.AUDIT_ONLY.value).strip().lower()
    aliases = {
        "audit": RuntimeEnforcementMode.AUDIT_ONLY.value,
        "audit_only": RuntimeEnforcementMode.AUDIT_ONLY.value,
        "dryrun": RuntimeEnforcementMode.DRY_RUN.value,
        "dry_run": RuntimeEnforcementMode.DRY_RUN.value,
        "enforce": RuntimeEnforcementMode.ENFORCE.value,
    }
    return aliases.get(value, RuntimeEnforcementMode.AUDIT_ONLY.value)


def runtime_enforcement_decision(
    transition_payload: Any,
    *,
    mode: RuntimeEnforcementMode | str = RuntimeEnforcementMode.AUDIT_ONLY,
    source: str = "",
    metadata: dict[str, Any] | None = None,
) -> RuntimeEnforcementDecision:
    payload = runtime_enforcement_readiness_payload(
        transition_payload,
        source=source,
        metadata=metadata,
    )
    normalized_mode = normalize_runtime_enforcement_mode(mode)
    classification = str(payload.get("enforcement_classification") or "")
    safe_to_enforce = bool(payload.get("safe_to_enforce", False))
    block_candidate = (
        classification == READINESS_BLOCK_RECOMMENDED
        and safe_to_enforce
    )
    evidence_present = isinstance(payload.get("transition_evidence"), dict) and bool(
        payload.get("transition_evidence")
    )
    evidence_required = bool(
        payload.get("evidence_required", payload.get("from_status") != payload.get("to_status"))
    )

    blocked = bool(
        normalized_mode == RuntimeEnforcementMode.ENFORCE.value
        and block_candidate
    )
    would_block = bool(
        normalized_mode == RuntimeEnforcementMode.DRY_RUN.value
        and block_candidate
    )
    allowed = not blocked

    return RuntimeEnforcementDecision(
        allowed=allowed,
        blocked=blocked,
        would_block=would_block,
        mode=normalized_mode,
        classification=classification,
        safe_to_enforce=safe_to_enforce,
        reason=str(payload.get("enforcement_reason") or ""),
        evidence_required=evidence_required,
        evidence_present=evidence_present,
        source_status=str(payload.get("from_status") or ""),
        target_status=str(payload.get("to_status") or ""),
        transition=payload,
        metadata=copy.deepcopy(metadata) if isinstance(metadata, dict) else {},
    )


def apply_runtime_enforcement_decision(
    transition_payload: Any,
    *,
    mode: RuntimeEnforcementMode | str = RuntimeEnforcementMode.AUDIT_ONLY,
    source: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = runtime_enforcement_decision(
        transition_payload,
        mode=mode,
        source=source,
        metadata=metadata,
    )
    decision_snapshot = runtime_enforcement_decision_snapshot(decision)
    payload = {
        **(copy.deepcopy(transition_payload) if isinstance(transition_payload, dict) else {}),
        **decision.transition,
        "enforcement_mode": decision.mode,
        "enforcement_decision": decision_snapshot,
        "enforcement_decision_schema": decision_snapshot["schema"],
        "allowed": decision.transition.get("allowed", False),
        "enforcement_allowed": decision.allowed,
        "blocked": decision.blocked,
        "would_block": decision.would_block,
    }
    if decision.blocked:
        raise RuntimeTransitionBlockedError(decision)
    return payload


def is_transition_safe_to_enforce(classification: Any) -> bool:
    payload = classification if isinstance(classification, dict) else {}
    return bool(payload.get("safe_to_enforce", False))


def is_transition_review_required(classification: Any) -> bool:
    payload = classification if isinstance(classification, dict) else {}
    return bool(payload.get("review_required", False))


def is_transition_block_recommended(classification: Any) -> bool:
    payload = classification if isinstance(classification, dict) else {}
    return bool(payload.get("block_recommended", False))


def summarize_enforcement_readiness(items: Any) -> dict[str, int]:
    entries = list(items or [])
    counts = {
        "total": 0,
        READINESS_SAFE_TO_ENFORCE: 0,
        READINESS_REVIEW_REQUIRED: 0,
        READINESS_BLOCK_RECOMMENDED: 0,
        READINESS_OBSERVE_ONLY: 0,
    }
    for item in entries:
        payload = item if isinstance(item, dict) else {}
        if "enforcement_classification" not in payload:
            payload = runtime_enforcement_readiness_payload(payload)
        counts["total"] += 1
        if payload.get("safe_to_enforce"):
            counts[READINESS_SAFE_TO_ENFORCE] += 1
        if payload.get("review_required"):
            counts[READINESS_REVIEW_REQUIRED] += 1
        if payload.get("block_recommended"):
            counts[READINESS_BLOCK_RECOMMENDED] += 1
        if payload.get("observe_only"):
            counts[READINESS_OBSERVE_ONLY] += 1
    return counts
