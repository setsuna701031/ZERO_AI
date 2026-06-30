from __future__ import annotations

import pytest

from core.tasks.engineering_result_contract import (

    EngineeringResultContractError,
    normalize_engineering_result_contract,
    validate_engineering_result_contract,
)
pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def _base_result(**overrides):
    result = {
        "schema": "test.result.v1",
        "ok": True,
        "task_result": {"ok": True, "action": "unit_test"},
        "issues_found": [],
        "issues_deferred": [],
        "deferred_issues": [],
        "blocking_issues": [],
        "success_allowed": True,
    }
    result.update(overrides)
    return result


def test_contract_accepts_complete_success_result():
    result = validate_engineering_result_contract(_base_result())

    assert result["ok"] is True
    assert result["issues_found"] == []
    assert result["issues_deferred"] == []
    assert result["deferred_issues"] == []
    assert result["blocking_issues"] == []
    assert result["success_allowed"] is True


def test_contract_rejects_missing_issue_fields():
    broken = {
        "schema": "test.result.v1",
        "ok": True,
        "task_result": {"ok": True},
    }

    with pytest.raises(EngineeringResultContractError) as exc:
        validate_engineering_result_contract(broken)

    assert "missing_engineering_result_fields" in str(exc.value)
    assert "issues_found" in str(exc.value)
    assert "issues_deferred" in str(exc.value)
    assert "blocking_issues" in str(exc.value)
    assert "success_allowed" in str(exc.value)


def test_contract_rejects_blocking_issue_with_success_allowed_true():
    issue = {
        "issue_id": "blocker-1",
        "severity": "high",
        "blocks_current_task": True,
        "reason": "Current task cannot safely finish.",
    }

    with pytest.raises(EngineeringResultContractError) as exc:
        validate_engineering_result_contract(
            _base_result(
                issues_found=[issue],
                blocking_issues=[issue],
                success_allowed=True,
            )
        )

    assert "blocking_issues_require_success_allowed_false" in str(exc.value)


def test_contract_accepts_deferred_issue_without_blocking_success():
    issue = {
        "issue_id": "later-1",
        "severity": "medium",
        "recommended_action": "queue_for_next_package",
        "reason": "Found outside the current mainline.",
    }

    result = validate_engineering_result_contract(
        _base_result(
            issues_found=[issue],
            issues_deferred=[issue],
            deferred_issues=[issue],
            success_allowed=True,
        )
    )

    assert result["ok"] is True
    assert result["success_allowed"] is True
    assert result["issues_deferred"] == [issue]
    assert result["blocking_issues"] == []


def test_contract_normalizes_not_in_scope_issue_into_deferred():
    issue = {
        "issue_id": "scope-1",
        "severity": "low",
        "category": "not_in_scope",
        "reason": "Issue is real but outside_current_scope.",
    }

    result = normalize_engineering_result_contract(
        _base_result(
            issues_found=[issue],
            issues_deferred=[],
            deferred_issues=[],
        )
    )

    assert result["ok"] is True
    assert result["success_allowed"] is True
    assert result["issues_deferred"] == [issue]
    assert result["deferred_issues"] == [issue]


def test_contract_rejects_success_not_allowed_with_ok_true():
    with pytest.raises(EngineeringResultContractError) as exc:
        validate_engineering_result_contract(_base_result(ok=True, success_allowed=False))

    assert "success_not_allowed_requires_ok_false" in str(exc.value)
