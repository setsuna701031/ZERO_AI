from __future__ import annotations

import copy

from core.tasks.engineering_issue_summary import apply_engineering_issue_summary
from core.tasks.engineering_result_contract import validate_engineering_result_contract


class DummyReporter:
    def __init__(self, summary):
        self._summary = summary

    def build_summary(self):
        return self._summary


def test_apply_issue_summary_outputs_complete_contract_fields(tmp_path):
    result = apply_engineering_issue_summary(
        {
            "schema": "unit.result.v1",
            "ok": True,
            "mode": "unit_test",
            "goal_id": "goal-1",
        },
        repo_root=tmp_path,
        issue_reporter=DummyReporter({"issues": [], "blocking_issues": [], "success_allowed": True}),
    )

    assert result["task_result"]["goal_id"] == "goal-1"
    assert result["issues_found"] == []
    assert result["issues_deferred"] == []
    assert result["deferred_issues"] == []
    assert result["blocking_issues"] == []
    assert result["success_allowed"] is True
    assert validate_engineering_result_contract(result)["ok"] is True


def test_apply_issue_summary_blocks_success_for_blocking_issue(tmp_path):
    issue = {
        "issue_id": "blocker-1",
        "severity": "high",
        "blocks_current_task": True,
        "reason": "Must be fixed before the current task can finish.",
    }

    result = apply_engineering_issue_summary(
        {"schema": "unit.result.v1", "ok": True, "mode": "unit_test"},
        repo_root=tmp_path,
        issue_reporter=DummyReporter({"issues": [issue], "blocking_issues": [], "success_allowed": True}),
    )

    assert result["ok"] is False
    assert result["success_allowed"] is False
    assert result["blocking_issues"] == [issue]
    assert validate_engineering_result_contract(result)["ok"] is False


def test_apply_issue_summary_defers_not_in_scope_without_blocking(tmp_path):
    issue = {
        "issue_id": "scope-1",
        "severity": "low",
        "category": "not_in_scope",
        "reason": "This is outside_current_scope but must be reported.",
    }

    result = apply_engineering_issue_summary(
        {"schema": "unit.result.v1", "ok": True, "mode": "unit_test"},
        repo_root=tmp_path,
        issue_reporter=DummyReporter({"issues": [issue], "blocking_issues": [], "success_allowed": True}),
    )

    assert result["ok"] is True
    assert result["success_allowed"] is True
    assert result["issues_found"] == [issue]
    assert result["issues_deferred"] == [issue]
    assert result["deferred_issues"] == [issue]
    assert result["blocking_issues"] == []
    assert validate_engineering_result_contract(result)["ok"] is True


def test_apply_issue_summary_preserves_runtime_semantics_while_attaching_top_level_fields(tmp_path):
    nested_runtime = {
        "state": "complete",
        "ok": True,
        "iterations": [
            {
                "continuation_result": {
                    "ok": True,
                    "goal_lifecycle": {
                        "goal_state": "completed",
                        "failed_tasks": [],
                    },
                }
            }
        ],
    }
    nested_continuation = {
        "ok": True,
        "goal_lifecycle": {
            "goal_state": "completed",
            "failed_tasks": [],
        },
    }
    nested_decision = {"decision": "complete", "continuation_plan": {}}
    nested_lifecycle = {"goal_state": "completed", "failed_tasks": []}
    original = {
        "schema": "unit.result.v1",
        "ok": True,
        "mode": "unit_test",
        "runtime_result": nested_runtime,
        "continuation_result": nested_continuation,
        "adaptive_decision": nested_decision,
        "goal_lifecycle": nested_lifecycle,
    }
    before = copy.deepcopy(original)

    result = apply_engineering_issue_summary(
        original,
        repo_root=tmp_path,
        issue_reporter=DummyReporter({"issues": [], "blocking_issues": [], "success_allowed": True}),
    )

    assert result["runtime_result"] == before["runtime_result"]
    assert result["continuation_result"] == before["continuation_result"]
    assert result["adaptive_decision"] == before["adaptive_decision"]
    assert result["goal_lifecycle"] == before["goal_lifecycle"]
    assert original == before
    assert result["task_result"]["ok"] is True
    assert result["issues_found"] == []
    assert result["blocking_issues"] == []
    assert result["success_allowed"] is True
