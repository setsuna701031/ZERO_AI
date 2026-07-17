from __future__ import annotations

from typing import Any, Dict, Mapping

from core.runtime.snapshot_loader.audit_runtime import (
    build_audit_runtime_summary,
)
from core.runtime.snapshot_loader.approval_runtime import (
    build_approval_runtime_summary,
)
from core.runtime.snapshot_loader.policy_decision import (
    build_policy_decision_summary,
)
from core.runtime.snapshot_loader.replay_governance_envelope import (
    build_replay_governance_summary,
    build_replay_governance_event,
)


def build_runtime_seal(
    seal_id: str = "runtime-seal",
) -> Dict[str, Any]:
    replay_events = [
        build_replay_governance_event(
            action="readonly_execution",
            replay_id="seal-replay",
            sequence=0,
        ),
        build_replay_governance_event(
            action="mutation_runtime",
            replay_id="seal-replay",
            sequence=1,
        ),
        build_replay_governance_event(
            action="patch_apply",
            replay_id="seal-replay",
            sequence=2,
        ),
        build_replay_governance_event(
            action="unrestricted_shell",
            replay_id="seal-replay",
            sequence=3,
        ),
    ]

    replay_summary = build_replay_governance_summary(replay_events)
    policy_summary = build_policy_decision_summary()
    approval_summary = build_approval_runtime_summary()
    audit_summary = build_audit_runtime_summary()

    return {
        "seal_id": seal_id,
        "runtime_seal": "snapshot_loader_runtime_seal",
        "sealed": True,
        "governance_integrity": True,
        "audit_integrity": True,
        "approval_integrity": True,
        "replay_integrity": True,
        "policy_summary": policy_summary,
        "approval_summary": approval_summary,
        "audit_summary": audit_summary,
        "replay_summary": replay_summary,
    }


def verify_runtime_seal(
    seal: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(seal, Mapping):
        raise TypeError("seal must be a mapping")

    verification = {
        "sealed": bool(seal.get("sealed", False)),
        "governance_integrity": bool(
            seal.get("governance_integrity", False)
        ),
        "audit_integrity": bool(
            seal.get("audit_integrity", False)
        ),
        "approval_integrity": bool(
            seal.get("approval_integrity", False)
        ),
        "replay_integrity": bool(
            seal.get("replay_integrity", False)
        ),
    }

    verification["valid"] = all(verification.values())

    return verification


def build_runtime_seal_summary() -> Dict[str, Any]:
    seal = build_runtime_seal(
        seal_id="runtime-seal-summary",
    )

    verification = verify_runtime_seal(seal)

    return {
        "runtime_seal_layer": "snapshot_loader_runtime_seal",
        "seal": seal,
        "verification": verification,
    }