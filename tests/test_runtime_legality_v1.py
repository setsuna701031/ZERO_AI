from __future__ import annotations

from dataclasses import dataclass

from core.runtime.runtime_legality import (
    RuntimeLegalityDecision,
    RuntimeLegalityEngine,
    evaluate_runtime_legality,
)


@dataclass(frozen=True)
class FakeGovernanceSnapshot:
    governance_id: str


@dataclass(frozen=True)
class FakeRuntimeConstitution:
    constitution_version: str
    allowed_actions: tuple[str, ...]
    review_required_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]


def _constitution() -> FakeRuntimeConstitution:
    return FakeRuntimeConstitution(
        constitution_version="runtime-constitution-v1",
        allowed_actions=(
            "read_file",
            "list_directory",
            "runtime_status",
        ),
        review_required_actions=(
            "apply_patch",
            "write_file",
            "execute_python",
        ),
        blocked_actions=(
            "delete_repo",
            "force_push",
            "system_wipe",
        ),
    )


def _governance() -> FakeGovernanceSnapshot:
    return FakeGovernanceSnapshot(governance_id="governance-snapshot-001")


def test_runtime_legality_allows_read_file() -> None:
    decision = RuntimeLegalityEngine().evaluate_action(
        action_type="read_file",
        risk_level="low",
        governance_snapshot=_governance(),
        constitution=_constitution(),
    )

    assert isinstance(decision, RuntimeLegalityDecision)
    assert decision.allowed is True
    assert decision.requires_review is False
    assert decision.blocked is False
    assert decision.decision == "ALLOW"
    assert decision.action_type == "read_file"
    assert decision.risk_level == "low"
    assert decision.governance_id == "governance-snapshot-001"
    assert decision.constitution_version == "runtime-constitution-v1"
    assert decision.violated_rules == []


def test_runtime_legality_requires_review_for_apply_patch() -> None:
    decision = RuntimeLegalityEngine().evaluate_action(
        action_type="apply_patch",
        risk_level="medium",
        governance_snapshot=_governance(),
        constitution=_constitution(),
    )

    assert decision.allowed is False
    assert decision.requires_review is True
    assert decision.blocked is False
    assert decision.decision == "REVIEW"
    assert decision.action_type == "apply_patch"
    assert decision.risk_level == "medium"
    assert decision.governance_id == "governance-snapshot-001"
    assert decision.constitution_version == "runtime-constitution-v1"


def test_runtime_legality_blocks_system_wipe() -> None:
    decision = RuntimeLegalityEngine().evaluate_action(
        action_type="system_wipe",
        risk_level="critical",
        governance_snapshot=_governance(),
        constitution=_constitution(),
    )

    assert decision.allowed is False
    assert decision.requires_review is False
    assert decision.blocked is True
    assert decision.decision == "BLOCK"
    assert decision.action_type == "system_wipe"
    assert decision.risk_level == "critical"
    assert decision.governance_id == "governance-snapshot-001"
    assert decision.constitution_version == "runtime-constitution-v1"
    assert "runtime.action.blocked:system_wipe" in decision.violated_rules


def test_runtime_legality_unknown_action_defaults_to_review() -> None:
    decision = RuntimeLegalityEngine().evaluate_action(
        action_type="unknown_runtime_action",
        risk_level="unknown",
        governance_snapshot=_governance(),
        constitution=_constitution(),
    )

    assert decision.allowed is False
    assert decision.requires_review is True
    assert decision.blocked is False
    assert decision.decision == "REVIEW"
    assert "runtime.action.not_explicitly_allowed" in decision.violated_rules


def test_runtime_legality_missing_action_is_blocked() -> None:
    decision = RuntimeLegalityEngine().evaluate_action(
        action_type="",
        risk_level="unknown",
        governance_snapshot=_governance(),
        constitution=_constitution(),
    )

    assert decision.allowed is False
    assert decision.requires_review is False
    assert decision.blocked is True
    assert decision.decision == "BLOCK"
    assert "runtime.action_type.required" in decision.violated_rules


def test_runtime_legality_supports_mapping_inputs() -> None:
    decision = evaluate_runtime_legality(
        action_type="write_file",
        risk_level="medium",
        governance_snapshot={"snapshot_id": "governance-map-001"},
        constitution={
            "version": "runtime-constitution-map-v1",
            "allowed_actions": ["read_file"],
            "review_required_actions": ["write_file"],
            "blocked_actions": ["system_wipe"],
        },
    )

    assert decision.allowed is False
    assert decision.requires_review is True
    assert decision.blocked is False
    assert decision.decision == "REVIEW"
    assert decision.governance_id == "governance-map-001"
    assert decision.constitution_version == "runtime-constitution-map-v1"


def test_runtime_legality_decision_to_dict_is_audit_friendly() -> None:
    decision = RuntimeLegalityEngine().evaluate_action(
        action_type="read_file",
        risk_level="low",
        governance_snapshot=_governance(),
        constitution=_constitution(),
    )

    payload = decision.to_dict()

    assert payload["decision"] == "ALLOW"
    assert payload["allowed"] is True
    assert payload["requires_review"] is False
    assert payload["blocked"] is False
    assert payload["action_type"] == "read_file"
    assert payload["risk_level"] == "low"
    assert payload["governance_id"] == "governance-snapshot-001"
    assert payload["constitution_version"] == "runtime-constitution-v1"
    assert payload["violated_rules"] == []
