from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_authority_source_closure import (

    CANONICAL_EXECUTION_AUTHORITY_SOURCE,
    NON_MAINLINE_REPORTING_RULES,
    OBSERVED_NON_MAINLINE_AUTHORITY_SURFACES,
    RUNTIME_AUTHORITY_SOURCE_CLOSURE_TARGETS,
    audit_runtime_authority_source_closure,
)
from core.runtime.runtime_capability_tokens import RuntimeCapabilityTokenManager
from core.runtime.runtime_execution_authority_policy import RuntimeExecutionAuthorityPolicy
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



ROOT = Path(__file__).resolve().parents[1]


def test_execution_authority_policy_is_the_single_named_decision_source() -> None:
    assert CANONICAL_EXECUTION_AUTHORITY_SOURCE == "RuntimeExecutionAuthorityPolicy"

    policy = RuntimeExecutionAuthorityPolicy()

    dispatcher = policy.evaluate(
        source="runtime_dispatcher",
        action_type="apply_patch",
        metadata={"side_effect": True},
    )
    assert dispatcher.blocked is True
    assert dispatcher.reason == "non_canonical_execution_authority"

    task_runner = policy.evaluate(
        source="task_runner",
        action_type="shell",
        metadata={"side_effect": True},
    )
    assert task_runner.blocked is True
    assert task_runner.reason == "helper_bridge_cannot_execute_side_effect"

    gateway = policy.evaluate(
        source="core.runtime.execution_gateway",
        action_type="execute",
        metadata={"side_effect": True},
    )
    assert gateway.allowed is True
    assert gateway.reason == "canonical_execution_authority"


def test_capability_token_manager_is_not_named_as_authority_manager() -> None:
    doc = RuntimeCapabilityTokenManager.__doc__ or ""
    assert "not execution authority" in doc
    assert "authority manager" not in doc.lower()


def test_static_closure_audit_has_no_blocking_findings_and_reports_observations() -> None:
    report = audit_runtime_authority_source_closure(root=ROOT)

    assert report["schema"] == "zero.runtime_authority_source_closure.audit.v1"
    assert report["missing_targets"] == []
    assert report["blocking_findings"] == []
    assert report["closed"] is True

    observations = report["observed_non_mainline_authority_surfaces"]
    assert observations == list(OBSERVED_NON_MAINLINE_AUTHORITY_SURFACES)
    assert any("runtime_mutation_gateway.py" in item["surface"] for item in observations)
    assert any("runtime_dispatcher.py" in item["surface"] for item in observations)


def test_audit_document_names_targets_and_non_mainline_reporting_rules() -> None:
    doc = (ROOT / "docs/architecture/runtime_authority_source_closure.md").read_text(
        encoding="utf-8"
    )

    assert "RuntimeExecutionAuthorityPolicy" in doc
    assert "RuntimeCapabilityTokenManager is not execution authority" in doc

    for target in RUNTIME_AUTHORITY_SOURCE_CLOSURE_TARGETS:
        assert target in doc

    for rule in NON_MAINLINE_REPORTING_RULES:
        assert rule in doc

    assert "Report, do not silently skip" in doc
