from __future__ import annotations

import pytest

from core.runtime.snapshot_loader.audit_runtime import (
    build_audit_lineage,
    build_audit_record,
    build_audit_runtime_summary,
)


def test_audit_record_for_readonly_execution() -> None:
    record = build_audit_record(
        action="readonly_execution",
        payload={"task": "inspect"},
        audit_id="audit-readonly",
        source="test",
    )

    assert record["audit_id"] == "audit-readonly"
    assert record["source"] == "test"
    assert record["action"] == "readonly_execution"
    assert record["payload"] == {"task": "inspect"}
    assert record["classification"] == "readonly"
    assert record["risk_level"] == "low"
    assert record["policy_decision"] == "allow"
    assert record["approval_state"] == "not_required"
    assert record["audit_required"] is False
    assert record["governance_critical"] is False


def test_audit_record_for_mutation_runtime() -> None:
    record = build_audit_record(
        action="mutation_runtime",
        payload={"target": "core/runtime/example.py"},
        audit_id="audit-mutation",
    )

    assert record["action"] == "mutation_runtime"
    assert record["classification"] == "mutation"
    assert record["risk_level"] == "high"
    assert record["policy_decision"] == "review_required"
    assert record["approval_state"] == "pending_review"
    assert record["approval_required"] is True
    assert record["audit_required"] is True
    assert record["governance_critical"] is True
    assert record["mutation_capable"] is True


def test_audit_record_for_patch_apply() -> None:
    record = build_audit_record(
        action="patch_apply",
        payload={"patch": "diff --git ..."},
        audit_id="audit-patch",
    )

    assert record["action"] == "patch_apply"
    assert record["classification"] == "patch"
    assert record["risk_level"] == "high"
    assert record["policy_decision"] == "review_required"
    assert record["approval_state"] == "pending_review"
    assert record["audit_required"] is True
    assert record["replay_sensitive"] is True


def test_audit_record_for_unrestricted_shell() -> None:
    record = build_audit_record(
        action="unrestricted_shell",
        payload={"command": "dir"},
        audit_id="audit-shell",
    )

    assert record["action"] == "unrestricted_shell"
    assert record["classification"] == "shell"
    assert record["risk_level"] == "critical"
    assert record["policy_decision"] == "deny"
    assert record["approval_state"] == "governance_locked"
    assert record["approval_required"] is True
    assert record["audit_required"] is True
    assert record["governance_critical"] is True


def test_audit_lineage_contract() -> None:
    records = [
        build_audit_record("readonly_execution", audit_id="a1"),
        build_audit_record("mutation_runtime", audit_id="a2"),
        build_audit_record("patch_apply", audit_id="a3"),
        build_audit_record("unrestricted_shell", audit_id="a4"),
    ]

    lineage = build_audit_lineage(
        records=records,
        lineage_id="lineage-1",
    )

    assert lineage["lineage_id"] == "lineage-1"
    assert lineage["record_count"] == 4
    assert lineage["actions"] == [
        "readonly_execution",
        "mutation_runtime",
        "patch_apply",
        "unrestricted_shell",
    ]
    assert lineage["policy_decisions"] == [
        "allow",
        "review_required",
        "review_required",
        "deny",
    ]
    assert lineage["approval_states"] == [
        "not_required",
        "pending_review",
        "pending_review",
        "governance_locked",
    ]
    assert lineage["audit_required_actions"] == [
        "mutation_runtime",
        "patch_apply",
        "unrestricted_shell",
    ]
    assert lineage["governance_critical_actions"] == [
        "mutation_runtime",
        "patch_apply",
        "unrestricted_shell",
    ]


def test_audit_lineage_rejects_non_list_records() -> None:
    with pytest.raises(TypeError):
        build_audit_lineage(("not", "a", "list"))  # type: ignore[arg-type]


def test_audit_runtime_summary_contract() -> None:
    summary = build_audit_runtime_summary()

    assert summary["audit_runtime"] == "snapshot_loader_audit_runtime"
    assert summary["audit_required_actions"] == [
        "mutation_runtime",
        "patch_apply",
        "unrestricted_shell",
    ]
    assert summary["governance_critical_actions"] == [
        "mutation_runtime",
        "patch_apply",
        "unrestricted_shell",
    ]
    assert len(summary["records"]) == 4
    assert summary["lineage"]["record_count"] == 4