from __future__ import annotations

from pathlib import Path

from core.tasks.runtime_repair_apply_transaction import (
    abort_runtime_repair_apply_transaction,
    apply_runtime_repair_transaction_sandbox,
    build_runtime_repair_commit_preview,
    build_runtime_repair_apply_plan,
    build_runtime_repair_audit_bundle,
    build_runtime_repair_commit_artifact,
    build_runtime_repair_knowledge_snapshot,
    build_runtime_repair_knowledge_index,
    build_runtime_repair_similarity_query,
    build_runtime_repair_candidate_explanations,
    build_runtime_repair_decision_trace,
    build_runtime_repair_governance_report,
    build_runtime_repair_recommendation_draft,
    build_runtime_repair_recommendation_provenance,
    build_runtime_repair_review_request,
    build_runtime_repair_lineage_graph,
    build_runtime_repair_apply_transaction,
    build_runtime_repair_apply_transactions,
    consume_runtime_repair_commit_token,
    consume_runtime_repair_commit_session,
    create_runtime_repair_lineage_node,
    create_runtime_repair_recommendation_review,
    create_runtime_repair_commit_intent,
    commit_runtime_repair_transaction_temp_workspace,
    final_precheck_runtime_repair_commit,
    evaluate_runtime_repair_policy,
    issue_runtime_repair_commit_token,
    open_runtime_repair_commit_session,
    approve_runtime_repair_review,
    approve_runtime_repair_recommendation_review,
    assess_runtime_repair_risk,
    preflight_runtime_repair_apply_transaction,
    replay_runtime_repair_commit_artifact,
    revoke_runtime_repair_commit_token,
    revoke_runtime_repair_commit_session,
    reject_runtime_repair_review,
    reject_runtime_repair_recommendation_review,
    summarize_runtime_repair_apply_transaction,
    validate_runtime_repair_commit_intent,
    validate_runtime_repair_commit_artifact,
    validate_runtime_repair_knowledge_snapshot,
    validate_runtime_repair_knowledge_index,
    validate_runtime_repair_lineage_graph,
    validate_runtime_repair_commit_session,
    validate_runtime_repair_commit_token,
    query_runtime_repair_knowledge_index,
    retrieve_runtime_repair_candidates,
    explain_runtime_repair_candidate_match,
    validate_runtime_repair_candidate_explanations,
    validate_runtime_repair_candidate_retrieval,
    validate_runtime_repair_decision_trace,
    validate_runtime_repair_governance_report,
    validate_runtime_repair_policy_evaluation,
    validate_runtime_repair_recommendation_draft,
    validate_runtime_repair_recommendation_provenance,
    validate_runtime_repair_recommendation_review,
    validate_runtime_repair_risk_assessment,
    verify_runtime_repair_reproducibility,
)


def _ready_preview():
    return {
        "task_id": "task_001",
        "proposal_id": "proposal_001",
        "preview_allowed": True,
        "apply_allowed": False,
        "target_path": "workspace/tasks/task_001/example.py",
        "diff": "--- a/example.py\n+++ b/example.py\n- old\n+ new",
        "diff_line_count": 4,
        "added_lines": 1,
        "removed_lines": 1,
    }


def _staged_transaction():
    return {
        "transaction_id": "repair_tx_test_001",
        "task_id": "task_001",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "staged",
        "operations": [
            {
                "op_type": "patch",
                "target_path": "project/example.py",
                "patch": "--- a/example.py\n+++ b/example.py\n- old\n+ new",
            }
        ],
    }


def test_apply_transaction_stages_preview_without_mutation_permission():
    result = build_runtime_repair_apply_transaction(
        _ready_preview(),
        operator="tester",
    )

    assert result["ok"] is True
    assert result["transaction_status"] == "staged"
    assert result["staged"] is True
    assert result["transaction_id"].startswith("repair_tx_")
    assert result["operator"] == "tester"

    assert result["mutation_allowed"] is False
    assert result["apply_allowed"] is False
    assert result["write_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["schedule_allowed"] is False

    assert result["allowed_next_action"] == "create_rollback_snapshot"
    assert result["rollback_plan"]["snapshot_required"] is True
    assert result["rollback_plan"]["snapshot_status"] == "not_created"
    assert result["staged_patch"]["target_path"] == "workspace/tasks/task_001/example.py"


def test_apply_transaction_blocks_preview_that_is_not_allowed():
    preview = _ready_preview()
    preview["preview_allowed"] = False

    result = build_runtime_repair_apply_transaction(preview)

    assert result["transaction_status"] == "blocked"
    assert result["staged"] is False
    assert "patch_preview_not_allowed" in result["blocked_reasons"]
    assert result["allowed_next_action"] == "inspect_transaction_block"
    assert result["apply_allowed"] is False


def test_apply_transaction_blocks_missing_target_or_diff():
    result = build_runtime_repair_apply_transaction(
        {
            "preview_allowed": True,
            "apply_allowed": False,
            "target_path": "",
            "diff": "",
        }
    )

    assert result["transaction_status"] == "blocked"
    assert "target_path_missing" in result["blocked_reasons"]
    assert "diff_missing" in result["blocked_reasons"]


def test_apply_transaction_blocks_if_preview_claims_apply_allowed():
    preview = _ready_preview()
    preview["apply_allowed"] = True

    result = build_runtime_repair_apply_transaction(preview)

    assert result["transaction_status"] == "blocked"
    assert "unexpected_apply_allowed_in_preview_layer" in result["blocked_reasons"]
    assert result["apply_allowed"] is False


def test_apply_transaction_id_is_stable_for_same_preview():
    first = build_runtime_repair_apply_transaction(_ready_preview())
    second = build_runtime_repair_apply_transaction(_ready_preview())

    assert first["transaction_id"] == second["transaction_id"]


def test_apply_transactions_accepts_list_input():
    results = build_runtime_repair_apply_transactions([
        _ready_preview(),
        _ready_preview(),
    ])

    assert len(results) == 2
    assert all(item["transaction_status"] == "staged" for item in results)


def test_summarize_apply_transaction_returns_safe_compact_summary():
    transaction = build_runtime_repair_apply_transaction(_ready_preview())
    summary = summarize_runtime_repair_apply_transaction(transaction)

    assert summary["transaction_status"] == "staged"
    assert summary["staged_patch_count"] == 1
    assert summary["mutation_allowed"] is False
    assert summary["apply_allowed"] is False
    assert summary["allowed_next_action"] == "create_rollback_snapshot"


def test_valid_staged_transaction_preflight_passes(tmp_path):
    transaction = _staged_transaction()

    result = preflight_runtime_repair_apply_transaction(
        transaction,
        workspace_root=tmp_path,
        allowed_roots=["project"],
    )

    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["transaction_id"] == "repair_tx_test_001"
    assert result["checked_at"]


def test_preflight_missing_required_field_fails(tmp_path):
    transaction = _staged_transaction()
    transaction.pop("created_at")

    result = preflight_runtime_repair_apply_transaction(
        transaction,
        workspace_root=tmp_path,
        allowed_roots=["project"],
    )

    assert result["ok"] is False
    assert "missing_required_field:created_at" in result["blockers"]


def test_preflight_invalid_operation_fails(tmp_path):
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "target_path": "project/example.py",
        }
    ]

    result = preflight_runtime_repair_apply_transaction(
        transaction,
        workspace_root=tmp_path,
        allowed_roots=["project"],
    )

    assert result["ok"] is False
    assert "invalid_operation:0:op_type_missing" in result["blockers"]
    assert "invalid_operation:0:payload_missing" in result["blockers"]


def test_preflight_unsafe_target_path_fails(tmp_path):
    transaction = _staged_transaction()
    transaction["operations"][0]["target_path"] = "../outside.py"

    result = preflight_runtime_repair_apply_transaction(
        transaction,
        workspace_root=tmp_path,
        allowed_roots=["project"],
    )

    assert result["ok"] is False
    assert "invalid_operation:0:unsafe_target_path" in result["blockers"]


def test_failed_preflight_can_abort_transaction(tmp_path):
    transaction = _staged_transaction()
    transaction["operations"][0].pop("patch")
    preflight = preflight_runtime_repair_apply_transaction(
        transaction,
        workspace_root=tmp_path,
        allowed_roots=["project"],
    )

    aborted = abort_runtime_repair_apply_transaction(
        transaction,
        preflight_result=preflight,
    )

    assert preflight["ok"] is False
    assert aborted["status"] == "aborted"
    assert aborted["transaction_status"] == "aborted"
    assert aborted["staged"] is False
    assert aborted["reason"] == "invalid_operation:0:payload_missing"
    assert aborted["aborted_at"]
    assert transaction["status"] == "staged"


def test_aborted_transaction_cannot_be_treated_as_ready(tmp_path):
    transaction = abort_runtime_repair_apply_transaction(
        _staged_transaction(),
        reason="operator_cancelled",
    )

    result = preflight_runtime_repair_apply_transaction(
        transaction,
        workspace_root=tmp_path,
        allowed_roots=["project"],
    )

    assert result["ok"] is False
    assert "transaction_aborted" in result["blockers"]


def test_dry_run_apply_plan_builds_correctly():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/new.py",
            "content": "print('new')",
        },
        {
            "op_type": "patch_file",
            "target_path": "project/example.py",
            "patch": "--- a/example.py\n+++ b/example.py\n- old\n+ new",
        },
    ]

    plan = build_runtime_repair_apply_plan(transaction)

    assert plan["transaction_id"] == "repair_tx_test_001"
    assert plan["operation_count"] == 2
    assert plan["affected_files"] == ["project/example.py", "project/new.py"]
    assert plan["warnings"] == []
    assert plan["ready"] is True
    assert plan["generated_at"]


def test_dry_run_apply_plan_affected_files_deduplicated():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/./same.py",
            "content": "one",
        },
        {
            "op_type": "patch_file",
            "target_path": "project/nested/../same.py",
            "patch": "patch",
        },
    ]

    plan = build_runtime_repair_apply_plan(transaction)

    assert plan["affected_files"] == ["project/same.py"]


def test_dry_run_apply_plan_aborted_transaction_not_ready():
    transaction = abort_runtime_repair_apply_transaction(
        _staged_transaction(),
        reason="operator_cancelled",
    )

    plan = build_runtime_repair_apply_plan(transaction)

    assert plan["ready"] is False
    assert "transaction_aborted" in plan["warnings"]


def test_dry_run_apply_plan_invalid_transaction_not_ready():
    transaction = _staged_transaction()
    transaction.pop("operations")

    plan = build_runtime_repair_apply_plan(transaction)

    assert plan["ready"] is False
    assert plan["operation_count"] == 0
    assert "missing_required_field:operations" in plan["warnings"]


def test_dry_run_apply_plan_operation_preview_generated():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/write.py",
            "content": "content",
            "mode": "replace",
        },
        {
            "op_type": "patch_file",
            "target_path": "project/patch.py",
            "patch": "patch",
        },
        {
            "op_type": "delete_file",
            "target_path": "project/delete.py",
            "payload": {"confirm": True},
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]

    plan = build_runtime_repair_apply_plan(transaction)

    assert plan["operation_preview"] == [
        {
            "op_type": "write_file",
            "target_path": "project/write.py",
            "mode": "replace",
            "summary": "would write content",
        },
        {
            "op_type": "patch_file",
            "target_path": "project/patch.py",
            "mode": "dry_run",
            "summary": "would apply patch",
        },
        {
            "op_type": "delete_file",
            "target_path": "project/delete.py",
            "mode": "dry_run",
            "summary": "would delete file",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "mode": "dry_run",
            "summary": "would execute command",
        },
    ]


def test_dry_run_apply_plan_deterministic_ordering_stable():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/z.py",
            "content": "z",
        },
        {
            "op_type": "write_file",
            "target_path": "project/a.py",
            "content": "a",
        },
        {
            "op_type": "write_file",
            "target_path": "project/m.py",
            "content": "m",
        },
    ]

    first = build_runtime_repair_apply_plan(transaction)
    second = build_runtime_repair_apply_plan(transaction)

    assert first["affected_files"] == ["project/a.py", "project/m.py", "project/z.py"]
    assert second["affected_files"] == first["affected_files"]


def test_sandbox_write_apply_success():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/new.py",
            "content": "print('sandbox')\n",
        }
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)

    sandbox_path = Path(result["sandbox_path"])
    assert result["success"] is True
    assert result["rollback_performed"] is False
    assert result["applied_operations"] == [
        {
            "index": 0,
            "op_type": "write_file",
            "target_path": "project/new.py",
        }
    ]
    assert (sandbox_path / "project" / "new.py").read_text(encoding="utf-8") == "print('sandbox')\n"


def test_sandbox_delete_apply_success():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/delete_me.py",
            "content": "temporary\n",
        },
        {
            "op_type": "delete_file",
            "target_path": "project/delete_me.py",
            "payload": {"confirm": True},
        },
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)

    sandbox_path = Path(result["sandbox_path"])
    assert result["success"] is True
    assert result["applied_operations"][1]["op_type"] == "delete_file"
    assert not (sandbox_path / "project" / "delete_me.py").exists()


def test_sandbox_failed_operation_triggers_rollback():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/partial.py",
            "content": "partial\n",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)

    assert result["success"] is False
    assert result["rollback_performed"] is True
    assert result["failed_operation"]["index"] == 1
    assert result["failed_operation"]["reason"] == "unsupported_operation:command"


def test_sandbox_no_partial_files_remain_after_rollback():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/partial.py",
            "content": "partial\n",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)

    assert result["success"] is False
    assert not Path(result["sandbox_path"]).exists()


def test_sandbox_apply_ordering_is_deterministic():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/first.py",
            "content": "first\n",
        },
        {
            "op_type": "patch_file",
            "target_path": "project/second.py",
            "patch": "--- a/second.py\n+++ b/second.py\n+second",
        },
        {
            "op_type": "delete_file",
            "target_path": "project/first.py",
            "payload": {"confirm": True},
        },
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)

    assert result["success"] is True
    assert [item["op_type"] for item in result["applied_operations"]] == [
        "write_file",
        "patch_file",
        "delete_file",
    ]
    assert [item["index"] for item in result["applied_operations"]] == [0, 1, 2]


def test_sandbox_path_traversal_blocked():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "../escape.py",
            "content": "escape\n",
        }
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)

    assert result["success"] is False
    assert result["rollback_performed"] is True
    assert "unsafe_target_path" in result["failed_operation"]["reason"]


def test_sandbox_cleaned_after_failure():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/partial.py",
            "content": "partial\n",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)

    assert result["success"] is False
    assert not Path(result["sandbox_path"]).exists()


def test_commit_preview_generated():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/new.py",
            "content": "new\n",
        }
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)
    preview = build_runtime_repair_commit_preview(result)

    assert preview["transaction_id"] == "repair_tx_test_001"
    assert preview["preview_ready"] is True
    assert preview["changed_files"] == [
        {
            "target_path": "project/new.py",
            "operation_type": "write_file",
            "before_exists": False,
            "after_exists": True,
            "content_changed": True,
        }
    ]
    assert preview["generated_at"]


def test_commit_preview_changed_files_detected():
    transaction = _staged_transaction()
    transaction["sandbox_files"] = {
        "project/delete.py": "delete me\n",
        "project/patch.py": "old\n",
    }
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/write.py",
            "content": "write\n",
        },
        {
            "op_type": "patch_file",
            "target_path": "project/patch.py",
            "patch": "--- a/patch.py\n+++ b/patch.py\n-old\n+new",
        },
        {
            "op_type": "delete_file",
            "target_path": "project/delete.py",
            "payload": {"confirm": True},
        },
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)
    preview = build_runtime_repair_commit_preview(result)

    assert preview["changed_files"] == [
        {
            "target_path": "project/delete.py",
            "operation_type": "delete_file",
            "before_exists": True,
            "after_exists": False,
            "content_changed": True,
        },
        {
            "target_path": "project/patch.py",
            "operation_type": "patch_file",
            "before_exists": True,
            "after_exists": True,
            "content_changed": True,
        },
        {
            "target_path": "project/write.py",
            "operation_type": "write_file",
            "before_exists": False,
            "after_exists": True,
            "content_changed": True,
        },
    ]


def test_commit_preview_rollback_marked_failed():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/partial.py",
            "content": "partial\n",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)
    preview = build_runtime_repair_commit_preview(result)

    assert preview["preview_ready"] is False
    assert preview["diff_summary"]["rollback"] is True
    assert preview["diff_summary"]["failures"] == 1
    assert preview["changed_files"] == []
    assert preview["operation_results"][0]["rollback_applied"] is True
    assert preview["operation_results"][1]["success"] is False


def test_commit_preview_deterministic_snapshot_ordering():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/z.py",
            "content": "z\n",
        },
        {
            "op_type": "write_file",
            "target_path": "project/a.py",
            "content": "a\n",
        },
        {
            "op_type": "write_file",
            "target_path": "project/m.py",
            "content": "m\n",
        },
    ]

    first = build_runtime_repair_commit_preview(apply_runtime_repair_transaction_sandbox(transaction))
    second = build_runtime_repair_commit_preview(apply_runtime_repair_transaction_sandbox(transaction))

    assert [item["target_path"] for item in first["changed_files"]] == [
        "project/a.py",
        "project/m.py",
        "project/z.py",
    ]
    assert first["changed_files"] == second["changed_files"]
    assert first["operation_results"] == second["operation_results"]


def test_commit_preview_diff_summary_counts_correct():
    transaction = _staged_transaction()
    transaction["sandbox_files"] = {
        "project/delete.py": "delete me\n",
        "project/patch.py": "old\n",
    }
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/write.py",
            "content": "write\n",
        },
        {
            "op_type": "patch_file",
            "target_path": "project/patch.py",
            "patch": "--- a/patch.py\n+++ b/patch.py\n-old\n+new",
        },
        {
            "op_type": "delete_file",
            "target_path": "project/delete.py",
            "payload": {"confirm": True},
        },
    ]

    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(transaction)
    )

    assert preview["diff_summary"] == {
        "total_files_changed": 3,
        "writes": 1,
        "patches": 1,
        "deletes": 1,
        "failures": 0,
        "rollback": False,
    }


def test_commit_preview_sandbox_only_snapshot_isolation(tmp_path):
    real_target = tmp_path / "project" / "real.py"
    real_target.parent.mkdir()
    real_target.write_text("real workspace\n", encoding="utf-8")

    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/real.py",
            "content": "sandbox only\n",
        }
    ]

    result = apply_runtime_repair_transaction_sandbox(transaction)
    preview = build_runtime_repair_commit_preview(result)

    assert preview["preview_ready"] is True
    assert real_target.read_text(encoding="utf-8") == "real workspace\n"
    assert Path(result["sandbox_path"]) != tmp_path


def test_review_request_generated():
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(
            {
                **_staged_transaction(),
                "operations": [
                    {
                        "op_type": "write_file",
                        "target_path": "project/new.py",
                        "content": "new\n",
                    }
                ],
            }
        )
    )

    request = build_runtime_repair_review_request(preview)

    assert request["transaction_id"] == "repair_tx_test_001"
    assert request["review_required"] is True
    assert request["review_status"] == "pending"
    assert request["risk_level"] == "medium"
    assert request["commit_allowed"] is False
    assert request["created_at"]


def test_pending_review_blocks_commit():
    preview = {
        "transaction_id": "repair_tx_test_001",
        "preview_ready": True,
        "changed_files": [],
        "diff_summary": {
            "total_files_changed": 0,
            "writes": 0,
            "patches": 0,
            "deletes": 0,
            "failures": 0,
            "rollback": False,
        },
    }

    request = build_runtime_repair_review_request(preview)

    assert request["review_status"] == "pending"
    assert request["commit_allowed"] is False


def test_approval_allows_commit():
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(
            {
                **_staged_transaction(),
                "operations": [
                    {
                        "op_type": "write_file",
                        "target_path": "project/new.py",
                        "content": "new\n",
                    }
                ],
            }
        )
    )
    request = build_runtime_repair_review_request(preview)

    approved = approve_runtime_repair_review(request, reviewer="human", note="looks good")

    assert approved["transaction_id"] == "repair_tx_test_001"
    assert approved["review_status"] == "approved"
    assert approved["approved_by"] == "human"
    assert approved["note"] == "looks good"
    assert approved["commit_allowed"] is True
    assert approved["approved_at"]


def test_rejection_blocks_commit():
    request = build_runtime_repair_review_request(
        {
            "transaction_id": "repair_tx_test_001",
            "preview_ready": True,
            "changed_files": [],
            "diff_summary": {
                "total_files_changed": 0,
                "writes": 0,
                "patches": 0,
                "deletes": 0,
                "failures": 0,
                "rollback": False,
            },
        }
    )

    rejected = reject_runtime_repair_review(request, reviewer="human", reason="needs changes")

    assert rejected["review_status"] == "rejected"
    assert rejected["rejected_by"] == "human"
    assert rejected["reason"] == "needs changes"
    assert rejected["commit_allowed"] is False
    assert rejected["rejected_at"]


def test_blocked_preview_cannot_be_approved():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/partial.py",
            "content": "partial\n",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(transaction)
    )
    request = build_runtime_repair_review_request(preview)

    approved = approve_runtime_repair_review(request, reviewer="human", note="override")

    assert request["risk_level"] == "blocked"
    assert approved["review_status"] == "blocked"
    assert approved["commit_allowed"] is False


def test_delete_operation_becomes_high_risk():
    transaction = _staged_transaction()
    transaction["sandbox_files"] = {"project/delete.py": "delete me\n"}
    transaction["operations"] = [
        {
            "op_type": "delete_file",
            "target_path": "project/delete.py",
            "payload": {"confirm": True},
        }
    ]
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(transaction)
    )

    request = build_runtime_repair_review_request(preview)

    assert request["risk_level"] == "high"
    assert "delete_operation" in request["reasons"]


def test_multi_file_change_becomes_high_risk():
    transaction = _staged_transaction()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/a.py",
            "content": "a\n",
        },
        {
            "op_type": "write_file",
            "target_path": "project/b.py",
            "content": "b\n",
        },
        {
            "op_type": "write_file",
            "target_path": "project/c.py",
            "content": "c\n",
        },
    ]
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(transaction)
    )

    request = build_runtime_repair_review_request(preview)

    assert request["risk_level"] == "high"
    assert "multi_file_change" in request["reasons"]


def test_commit_allowed_requires_explicit_approval():
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(
            {
                **_staged_transaction(),
                "operations": [
                    {
                        "op_type": "write_file",
                        "target_path": "project/new.py",
                        "content": "new\n",
                    }
                ],
            }
        )
    )

    request = build_runtime_repair_review_request(preview)

    assert preview["preview_ready"] is True
    assert request["commit_allowed"] is False
    assert approve_runtime_repair_review(request, "human", "approved")["commit_allowed"] is True


def _approved_review_result():
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(
            {
                **_staged_transaction(),
                "operations": [
                    {
                        "op_type": "write_file",
                        "target_path": "project/new.py",
                        "content": "new\n",
                    }
                ],
            }
        )
    )
    request = build_runtime_repair_review_request(preview)
    return approve_runtime_repair_review(request, reviewer="human", note="approved")


def test_approved_review_can_issue_token():
    token = issue_runtime_repair_commit_token(_approved_review_result())

    assert token["transaction_id"] == "repair_tx_test_001"
    assert token["token_id"].startswith("repair_commit_token_")
    assert token["approved_by"] == "human"
    assert token["commit_authorized"] is True
    assert token["token_status"] == "active"
    assert token["issued_at"]
    assert token["expires_at"]


def test_pending_review_cannot_issue_token():
    request = build_runtime_repair_review_request(
        {
            "transaction_id": "repair_tx_test_001",
            "preview_ready": True,
            "changed_files": [],
            "diff_summary": {
                "total_files_changed": 0,
                "writes": 0,
                "patches": 0,
                "deletes": 0,
                "failures": 0,
                "rollback": False,
            },
        }
    )

    token = issue_runtime_repair_commit_token(request)

    assert token["token_status"] == "revoked"
    assert token["commit_authorized"] is False
    assert validate_runtime_repair_commit_token(token)["valid"] is False


def test_rejected_review_cannot_issue_token():
    request = build_runtime_repair_review_request(
        {
            "transaction_id": "repair_tx_test_001",
            "preview_ready": True,
            "changed_files": [],
            "diff_summary": {
                "total_files_changed": 0,
                "writes": 0,
                "patches": 0,
                "deletes": 0,
                "failures": 0,
                "rollback": False,
            },
        }
    )
    rejected = reject_runtime_repair_review(request, reviewer="human", reason="no")

    token = issue_runtime_repair_commit_token(rejected)

    assert token["token_status"] == "revoked"
    assert token["commit_authorized"] is False


def test_expired_token_invalid():
    token = issue_runtime_repair_commit_token(_approved_review_result(), ttl_seconds=0)

    validation = validate_runtime_repair_commit_token(token)

    assert validation["valid"] is False
    assert validation["expired"] is True
    assert validation["reason"] == "token_expired"


def test_revoked_token_invalid():
    token = issue_runtime_repair_commit_token(_approved_review_result())
    revoked = revoke_runtime_repair_commit_token(token, reason="operator_cancelled")

    validation = validate_runtime_repair_commit_token(revoked)

    assert revoked["token_status"] == "revoked"
    assert revoked["commit_authorized"] is False
    assert validation["valid"] is False
    assert validation["revoked"] is True
    assert validation["reason"] == "token_revoked"


def test_consumed_token_unusable():
    token = issue_runtime_repair_commit_token(_approved_review_result())
    consumed = consume_runtime_repair_commit_token(token)

    validation = validate_runtime_repair_commit_token(consumed)

    assert consumed["token_status"] == "consumed"
    assert consumed["commit_authorized"] is False
    assert validation["valid"] is False
    assert validation["consumable"] is False
    assert validation["reason"] == "token_consumed"


def test_token_validation_works():
    token = issue_runtime_repair_commit_token(_approved_review_result())

    validation = validate_runtime_repair_commit_token(token)

    assert validation == {
        "valid": True,
        "reason": "valid",
        "expired": False,
        "revoked": False,
        "consumable": True,
    }


def test_token_ttl_enforced():
    token = issue_runtime_repair_commit_token(_approved_review_result(), ttl_seconds=60)

    assert token["expires_at_unix"] - token["issued_at_unix"] == 60


def test_commit_authorization_requires_valid_token():
    review = _approved_review_result()
    token = issue_runtime_repair_commit_token(review)
    consumed = consume_runtime_repair_commit_token(token)

    assert review["commit_allowed"] is True
    assert token["commit_authorized"] is True
    assert validate_runtime_repair_commit_token(token)["valid"] is True
    assert validate_runtime_repair_commit_token(consumed)["valid"] is False


def test_valid_token_creates_intent():
    review = _approved_review_result()
    token = issue_runtime_repair_commit_token(review)

    intent = create_runtime_repair_commit_intent(_staged_transaction(), review, token)

    assert intent["intent_id"].startswith("repair_commit_intent_")
    assert intent["transaction_id"] == "repair_tx_test_001"
    assert intent["review_id"] == review["review_id"]
    assert intent["token_id"] == token["token_id"]
    assert intent["created_by"] == "human"
    assert intent["intent_status"] == "pending_commit"
    assert intent["immutable_fields"]["transaction_id"] == "repair_tx_test_001"
    assert intent["immutable_fields"]["token_id"] == token["token_id"]
    assert intent["created_at"]


def test_expired_token_rejected_for_intent():
    review = _approved_review_result()
    token = issue_runtime_repair_commit_token(review, ttl_seconds=0)

    intent = create_runtime_repair_commit_intent(_staged_transaction(), review, token)

    assert intent["intent_status"] == "invalid"
    assert "token_invalid:token_expired" in intent["issues"]
    assert validate_runtime_repair_commit_intent(intent)["commit_ready"] is False


def test_rejected_review_rejected_for_intent():
    request = build_runtime_repair_review_request(
        {
            "transaction_id": "repair_tx_test_001",
            "preview_ready": True,
            "changed_files": [],
            "diff_summary": {
                "total_files_changed": 0,
                "writes": 0,
                "patches": 0,
                "deletes": 0,
                "failures": 0,
                "rollback": False,
            },
        }
    )
    rejected = reject_runtime_repair_review(request, reviewer="human", reason="no")
    token = issue_runtime_repair_commit_token(rejected)

    intent = create_runtime_repair_commit_intent(_staged_transaction(), rejected, token)

    assert intent["intent_status"] == "invalid"
    assert "review_not_approved" in intent["issues"]
    assert validate_runtime_repair_commit_intent(intent)["commit_ready"] is False


def test_commit_intent_immutable_fields_protected():
    review = _approved_review_result()
    token = issue_runtime_repair_commit_token(review)
    intent = create_runtime_repair_commit_intent(_staged_transaction(), review, token)

    intent["transaction_id"] = "tampered"
    validation = validate_runtime_repair_commit_intent(intent)

    assert validation["valid"] is False
    assert validation["immutable_ok"] is False
    assert validation["commit_ready"] is False
    assert "immutable_fields_modified" in validation["issues"]


def test_commit_intent_validation_works():
    review = _approved_review_result()
    token = issue_runtime_repair_commit_token(review)
    intent = create_runtime_repair_commit_intent(_staged_transaction(), review, token)

    validation = validate_runtime_repair_commit_intent(intent)

    assert validation == {
        "valid": True,
        "immutable_ok": True,
        "commit_ready": True,
        "issues": [],
    }


def test_commit_ready_requires_valid_intent():
    review = _approved_review_result()
    token = issue_runtime_repair_commit_token(review)
    intent = create_runtime_repair_commit_intent(_staged_transaction(), review, token)
    intent["token_snapshot"] = consume_runtime_repair_commit_token(intent["token_snapshot"])

    validation = validate_runtime_repair_commit_intent(intent)

    assert validation["valid"] is False
    assert validation["commit_ready"] is False
    assert "token_invalid:token_consumed" in validation["issues"]


def test_cancelled_intent_not_commit_ready():
    review = _approved_review_result()
    token = issue_runtime_repair_commit_token(review)
    intent = create_runtime_repair_commit_intent(_staged_transaction(), review, token)
    intent["intent_status"] = "cancelled"

    validation = validate_runtime_repair_commit_intent(intent)

    assert validation["commit_ready"] is False
    assert "intent_status:cancelled" in validation["issues"]


def test_commit_intent_deterministic_immutable_snapshot_stable():
    review = _approved_review_result()
    token = issue_runtime_repair_commit_token(review)

    first = create_runtime_repair_commit_intent(_staged_transaction(), review, token)
    second = create_runtime_repair_commit_intent(_staged_transaction(), review, token)

    assert first["intent_id"] == second["intent_id"]
    assert first["immutable_fields"] == second["immutable_fields"]
    assert first["immutable_digest"] == second["immutable_digest"]


def _valid_commit_intent():
    review = _approved_review_result()
    token = issue_runtime_repair_commit_token(review)
    return create_runtime_repair_commit_intent(_staged_transaction(), review, token)


def test_valid_intent_opens_session():
    intent = _valid_commit_intent()

    session = open_runtime_repair_commit_session(intent)

    assert session["session_id"].startswith("repair_commit_session_")
    assert session["transaction_id"] == "repair_tx_test_001"
    assert session["intent_id"] == intent["intent_id"]
    assert session["token_id"] == intent["token_id"]
    assert session["lease_status"] == "active"
    assert session["execution_allowed"] is True
    assert session["lease_started_at"]
    assert session["lease_expires_at"]


def test_expired_lease_invalid():
    session = open_runtime_repair_commit_session(_valid_commit_intent(), ttl_seconds=0)

    validation = validate_runtime_repair_commit_session(session)

    assert validation["valid"] is False
    assert validation["lease_active"] is False
    assert validation["execution_allowed"] is False
    assert "lease_expired" in validation["issues"]


def test_revoked_lease_invalid():
    session = open_runtime_repair_commit_session(_valid_commit_intent())
    revoked = revoke_runtime_repair_commit_session(session, reason="operator_cancelled")

    validation = validate_runtime_repair_commit_session(revoked)

    assert revoked["lease_status"] == "revoked"
    assert revoked["execution_allowed"] is False
    assert validation["valid"] is False
    assert "lease_status:revoked" in validation["issues"]


def test_consumed_lease_unusable():
    session = open_runtime_repair_commit_session(_valid_commit_intent())
    consumed = consume_runtime_repair_commit_session(session)

    validation = validate_runtime_repair_commit_session(consumed)

    assert consumed["lease_status"] == "consumed"
    assert consumed["execution_allowed"] is False
    assert validation["valid"] is False
    assert validation["lease_active"] is False
    assert "lease_status:consumed" in validation["issues"]


def test_execution_requires_active_lease():
    session = open_runtime_repair_commit_session(_valid_commit_intent())
    expired = dict(session)
    expired["lease_expires_at_unix"] = expired["lease_started_at_unix"]

    assert validate_runtime_repair_commit_session(session)["execution_allowed"] is True
    assert validate_runtime_repair_commit_session(expired)["execution_allowed"] is False


def test_lease_ttl_enforced():
    session = open_runtime_repair_commit_session(_valid_commit_intent(), ttl_seconds=120)

    assert session["lease_expires_at_unix"] - session["lease_started_at_unix"] == 120


def test_immutable_intent_required_for_session():
    intent = _valid_commit_intent()
    intent["transaction_id"] = "tampered"

    session = open_runtime_repair_commit_session(intent)
    validation = validate_runtime_repair_commit_session(session)

    assert session["lease_status"] == "revoked"
    assert session["execution_allowed"] is False
    assert "intent:immutable_fields_modified" in validation["issues"]


def test_commit_session_deterministic_lease_state_stable():
    intent = _valid_commit_intent()

    first = open_runtime_repair_commit_session(intent, ttl_seconds=120)
    second = open_runtime_repair_commit_session(intent, ttl_seconds=120)

    assert first["transaction_id"] == second["transaction_id"]
    assert first["intent_id"] == second["intent_id"]
    assert first["token_id"] == second["token_id"]
    assert first["lease_status"] == second["lease_status"] == "active"
    assert first["execution_allowed"] == second["execution_allowed"] is True
    assert first["lease_expires_at_unix"] - first["lease_started_at_unix"] == 120
    assert second["lease_expires_at_unix"] - second["lease_started_at_unix"] == 120


def _valid_commit_chain():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/new.py",
                "content": "new\n",
            }
        ],
    }
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(transaction)
    )
    request = build_runtime_repair_review_request(preview)
    review = approve_runtime_repair_review(request, reviewer="human", note="approved")
    token = issue_runtime_repair_commit_token(review)
    intent = create_runtime_repair_commit_intent(transaction, review, token)
    session = open_runtime_repair_commit_session(intent)
    return transaction, preview, review, token, intent, session


def test_valid_chain_passes_final_precheck():
    transaction, preview, review, token, intent, session = _valid_commit_chain()

    result = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    assert result["transaction_id"] == "repair_tx_test_001"
    assert result["precheck_ok"] is True
    assert result["commit_ready"] is True
    assert result["issues"] == []
    assert result["checked_at"]
    assert result["consistency_digest"]


def test_final_precheck_mismatched_transaction_id_fails():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    preview["transaction_id"] = "other_tx"

    result = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    assert result["precheck_ok"] is False
    assert "transaction_id_mismatch:preview" in result["issues"]


def test_final_precheck_modified_changed_files_fails():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    preview["changed_files"] = []

    result = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    assert result["commit_ready"] is False
    assert "changed_files_mismatch" in result["issues"]


def test_final_precheck_modified_diff_summary_fails():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    preview["diff_summary"] = {
        **preview["diff_summary"],
        "writes": 99,
    }

    result = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    assert result["commit_ready"] is False
    assert "diff_summary_mismatch" in result["issues"]


def test_final_precheck_invalid_token_fails():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    token = revoke_runtime_repair_commit_token(token, reason="cancelled")

    result = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    assert result["commit_ready"] is False
    assert "token_invalid:token_revoked" in result["issues"]


def test_final_precheck_invalid_intent_fails():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    intent["transaction_id"] = "tampered"

    result = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    assert result["commit_ready"] is False
    assert "intent:immutable_fields_modified" in result["issues"]
    assert "immutable_digest_modified" in result["issues"]


def test_final_precheck_expired_session_fails():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    session["lease_expires_at_unix"] = session["lease_started_at_unix"]

    result = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    assert result["commit_ready"] is False
    assert "session:lease_expired" in result["issues"]


def test_final_precheck_deterministic_consistency_digest_stable():
    transaction, preview, review, token, intent, session = _valid_commit_chain()

    first = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )
    second = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    assert first["consistency_digest"] == second["consistency_digest"]


def test_final_precheck_commit_ready_requires_all_gates():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    review["commit_allowed"] = False

    result = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    assert result["precheck_ok"] is False
    assert result["commit_ready"] is False
    assert "commit_not_allowed_by_review" in result["issues"]


def test_valid_precheck_commits_to_temp_workspace():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    precheck = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )

    temp_workspace = Path(result["temp_workspace_path"])
    assert result["commit_success"] is True
    assert result["commit_id"].startswith("repair_temp_commit_")
    assert result["committed_files"] == ["project/new.py"]
    assert result["session_consumed"] is True
    assert (temp_workspace / "project" / "new.py").read_text(encoding="utf-8") == "new\n"


def test_failed_precheck_blocks_temp_commit():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    precheck = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        revoke_runtime_repair_commit_token(token, "cancelled"),
        intent,
        session,
    )

    result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )

    assert result["commit_success"] is False
    assert result["temp_workspace_path"] == ""
    assert result["session_consumed"] is False
    assert "precheck_failed" in result["failed_operation"]["reason"]


def test_invalid_session_blocks_temp_commit():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    precheck = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )
    revoked_session = revoke_runtime_repair_commit_session(session, "cancelled")

    result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        revoked_session,
    )

    assert result["commit_success"] is False
    assert result["session_consumed"] is False
    assert "lease_status:revoked" in result["failed_operation"]["reason"]


def test_successful_temp_commit_consumes_session():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    precheck = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )

    assert result["commit_success"] is True
    assert result["session_consumed"] is True


def test_failed_temp_commit_rolls_back_workspace():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/partial.py",
            "content": "partial\n",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]
    precheck = final_precheck_runtime_repair_commit(
        {
            **transaction,
            "operations": [
                {
                    "op_type": "write_file",
                    "target_path": "project/new.py",
                    "content": "new\n",
                }
            ],
        },
        preview,
        review,
        token,
        intent,
        session,
    )

    result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )

    assert result["commit_success"] is False
    assert result["rollback_performed"] is True
    assert result["session_consumed"] is False
    assert not Path(result["temp_workspace_path"]).exists()


def test_temp_commit_path_traversal_blocked():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "../escape.py",
            "content": "escape\n",
        }
    ]
    precheck = final_precheck_runtime_repair_commit(
        {
            **transaction,
            "operations": [
                {
                    "op_type": "write_file",
                    "target_path": "project/new.py",
                    "content": "new\n",
                }
            ],
        },
        preview,
        review,
        token,
        intent,
        session,
    )

    result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )

    assert result["commit_success"] is False
    assert result["rollback_performed"] is True
    assert "unsafe_target_path" in result["failed_operation"]["reason"]


def test_temp_commit_committed_files_deterministic():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/z.py",
            "content": "z\n",
        },
        {
            "op_type": "write_file",
            "target_path": "project/a.py",
            "content": "a\n",
        },
        {
            "op_type": "write_file",
            "target_path": "project/m.py",
            "content": "m\n",
        },
    ]
    precheck = final_precheck_runtime_repair_commit(
        {
            **transaction,
            "operations": [
                {
                    "op_type": "write_file",
                    "target_path": "project/new.py",
                    "content": "new\n",
                }
            ],
        },
        preview,
        review,
        token,
        intent,
        session,
    )

    result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )

    assert result["commit_success"] is True
    assert result["committed_files"] == ["project/a.py", "project/m.py", "project/z.py"]


def test_temp_commit_formal_workspace_untouched(tmp_path):
    formal_file = tmp_path / "project" / "new.py"
    formal_file.parent.mkdir()
    formal_file.write_text("formal\n", encoding="utf-8")
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    precheck = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )

    result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )

    assert result["commit_success"] is True
    assert formal_file.read_text(encoding="utf-8") == "formal\n"
    assert Path(result["temp_workspace_path"]) != tmp_path


def _committed_temp_chain():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    precheck = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )
    commit_result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )
    return transaction, preview, review, token, intent, session, precheck, commit_result


def test_commit_artifact_generated_after_commit():
    transaction, preview, review, token, intent, session, precheck, commit_result = _committed_temp_chain()

    artifact = build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )

    assert artifact["artifact_id"].startswith("repair_commit_artifact_")
    assert artifact["transaction_id"] == "repair_tx_test_001"
    assert artifact["commit_id"] == commit_result["commit_id"]
    assert artifact["commit_success"] is True
    assert artifact["rollback_performed"] is False
    assert artifact["immutable_digest"]
    assert validate_runtime_repair_commit_artifact(artifact)["valid"] is True


def test_audit_bundle_generated():
    transaction, preview, review, token, intent, session, precheck, commit_result = _committed_temp_chain()
    artifact = build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )

    bundle = build_runtime_repair_audit_bundle(artifact)

    assert bundle["artifact_snapshot"]["artifact_id"] == artifact["artifact_id"]
    assert bundle["review_snapshot"]["review_status"] == "approved"
    assert bundle["token_snapshot"]["token_id"] == token["token_id"]
    assert bundle["intent_snapshot"]["intent_id"] == intent["intent_id"]
    assert bundle["session_snapshot"]["session_id"] == session["session_id"]
    assert bundle["preview_snapshot"]["transaction_id"] == "repair_tx_test_001"
    assert bundle["commit_snapshot"]["commit_id"] == commit_result["commit_id"]
    assert bundle["bundle_digest"]


def test_commit_artifact_immutable_protected():
    transaction, preview, review, token, intent, session, precheck, commit_result = _committed_temp_chain()
    artifact = build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )

    validation = validate_runtime_repair_commit_artifact(artifact)

    assert validation == {
        "valid": True,
        "immutable_ok": True,
        "digest_ok": True,
        "issues": [],
    }


def test_modified_commit_artifact_invalid():
    transaction, preview, review, token, intent, session, precheck, commit_result = _committed_temp_chain()
    artifact = build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )
    artifact["commit_id"] = "tampered"

    validation = validate_runtime_repair_commit_artifact(artifact)

    assert validation["valid"] is False
    assert validation["immutable_ok"] is False
    assert "immutable_fields_modified" in validation["issues"]


def test_audit_bundle_deterministic_digest_stable():
    transaction, preview, review, token, intent, session, precheck, commit_result = _committed_temp_chain()
    artifact = build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )

    first = build_runtime_repair_audit_bundle(artifact)
    second = build_runtime_repair_audit_bundle(artifact)

    assert first["bundle_digest"] == second["bundle_digest"]


def test_rollback_commit_artifact_recorded():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/partial.py",
            "content": "partial\n",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]
    precheck = final_precheck_runtime_repair_commit(
        {
            **transaction,
            "operations": [
                {
                    "op_type": "write_file",
                    "target_path": "project/new.py",
                    "content": "new\n",
                }
            ],
        },
        preview,
        review,
        token,
        intent,
        session,
    )
    commit_result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )

    artifact = build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )

    assert artifact["commit_success"] is False
    assert artifact["rollback_performed"] is True
    assert artifact["commit_id"] == ""


def test_commit_artifact_metadata_preserved():
    transaction, preview, review, token, intent, session, precheck, commit_result = _committed_temp_chain()

    artifact = build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )

    assert artifact["changed_files"] == preview["changed_files"]
    assert artifact["diff_summary"] == preview["diff_summary"]
    assert artifact["consistency_digest"] == precheck["consistency_digest"]
    assert artifact["created_at"]


def test_commit_artifact_session_token_review_linkage_preserved():
    transaction, preview, review, token, intent, session, precheck, commit_result = _committed_temp_chain()

    artifact = build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )

    assert artifact["review_id"] == review["review_id"]
    assert artifact["token_id"] == token["token_id"]
    assert artifact["intent_id"] == intent["intent_id"]
    assert artifact["session_id"] == session["session_id"]


def _committed_artifact():
    transaction, preview, review, token, intent, session, precheck, commit_result = _committed_temp_chain()
    return build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )


def test_artifact_replay_success():
    artifact = _committed_artifact()

    replay = replay_runtime_repair_commit_artifact(artifact)

    assert replay["replay_id"].startswith("repair_replay_")
    assert replay["artifact_id"] == artifact["artifact_id"]
    assert replay["replay_success"] is True
    assert replay["replay_changed_files"] == artifact["changed_files"]
    assert replay["replay_diff_summary"] == artifact["diff_summary"]
    assert replay["replay_digest"]
    assert replay["started_at"]
    assert replay["completed_at"]


def test_reproducibility_verification_passes():
    artifact = _committed_artifact()
    replay = replay_runtime_repair_commit_artifact(artifact)

    verification = verify_runtime_repair_reproducibility(artifact, replay)

    assert verification == {
        "reproducible": True,
        "changed_files_match": True,
        "diff_summary_match": True,
        "digest_match": True,
        "issues": [],
    }


def test_modified_replay_digest_fails():
    artifact = _committed_artifact()
    replay = replay_runtime_repair_commit_artifact(artifact)
    replay["replay_digest"] = "tampered"

    verification = verify_runtime_repair_reproducibility(artifact, replay)

    assert verification["reproducible"] is False
    assert verification["digest_match"] is False
    assert "digest_mismatch" in verification["issues"]


def test_replay_rollback_works():
    artifact = _committed_artifact()
    artifact["transaction_snapshot"]["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/partial.py",
            "content": "partial\n",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]

    replay = replay_runtime_repair_commit_artifact(artifact)

    assert replay["replay_success"] is False
    assert replay["replay_diff_summary"]["rollback"] is True
    assert replay["replay_changed_files"] == []


def test_replay_workspace_isolated(tmp_path):
    artifact = _committed_artifact()
    formal_file = tmp_path / "project" / "new.py"
    formal_file.parent.mkdir()
    formal_file.write_text("formal\n", encoding="utf-8")

    replay = replay_runtime_repair_commit_artifact(artifact)

    assert replay["replay_success"] is True
    assert Path(replay["replay_workspace"]) != tmp_path
    assert formal_file.read_text(encoding="utf-8") == "formal\n"


def test_deterministic_replay_ordering_stable():
    transaction, preview, review, token, intent, session = _valid_commit_chain()
    transaction["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/z.py",
            "content": "z\n",
        },
        {
            "op_type": "write_file",
            "target_path": "project/a.py",
            "content": "a\n",
        },
        {
            "op_type": "write_file",
            "target_path": "project/m.py",
            "content": "m\n",
        },
    ]
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(transaction)
    )
    request = build_runtime_repair_review_request(preview)
    review = approve_runtime_repair_review(request, reviewer="human", note="approved")
    token = issue_runtime_repair_commit_token(review)
    intent = create_runtime_repair_commit_intent(transaction, review, token)
    session = open_runtime_repair_commit_session(intent)
    precheck = final_precheck_runtime_repair_commit(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
    )
    commit_result = commit_runtime_repair_transaction_temp_workspace(
        transaction,
        preview,
        precheck,
        session,
    )
    artifact = build_runtime_repair_commit_artifact(
        transaction,
        preview,
        review,
        token,
        intent,
        session,
        precheck,
        commit_result,
    )

    first = replay_runtime_repair_commit_artifact(artifact)
    second = replay_runtime_repair_commit_artifact(artifact)

    assert [item["target_path"] for item in first["replay_changed_files"]] == [
        "project/a.py",
        "project/m.py",
        "project/z.py",
    ]
    assert first["replay_changed_files"] == second["replay_changed_files"]
    assert first["replay_diff_summary"] == second["replay_diff_summary"]
    assert first["replay_digest"] == second["replay_digest"]


def test_replay_does_not_mutate_original_artifact():
    artifact = _committed_artifact()
    original = {
        "changed_files": artifact["changed_files"],
        "diff_summary": artifact["diff_summary"],
        "immutable_digest": artifact["immutable_digest"],
    }

    replay_runtime_repair_commit_artifact(artifact)

    assert artifact["changed_files"] == original["changed_files"]
    assert artifact["diff_summary"] == original["diff_summary"]
    assert artifact["immutable_digest"] == original["immutable_digest"]


def test_replay_cleanup_after_failure():
    artifact = _committed_artifact()
    artifact["transaction_snapshot"]["operations"] = [
        {
            "op_type": "write_file",
            "target_path": "project/partial.py",
            "content": "partial\n",
        },
        {
            "op_type": "command",
            "target_path": "project",
            "payload": {"command": "pytest"},
        },
    ]

    replay = replay_runtime_repair_commit_artifact(artifact)

    assert replay["replay_success"] is False
    assert not Path(replay["replay_workspace"]).exists()


def _derived_artifact(parent, artifact_id, lineage_type="replay"):
    derived = dict(parent)
    derived["artifact_id"] = artifact_id
    derived["parent_artifact_id"] = parent["artifact_id"]
    derived["root_artifact_id"] = parent.get("root_artifact_id", parent["artifact_id"])
    derived["lineage_depth"] = int(parent.get("lineage_depth") or 0) + 1
    derived["lineage_type"] = lineage_type
    return derived


def test_original_artifact_creates_root_node():
    artifact = _committed_artifact()

    node = create_runtime_repair_lineage_node(artifact)

    assert node["artifact_id"] == artifact["artifact_id"]
    assert node["parent_artifact_id"] == ""
    assert node["root_artifact_id"] == artifact["artifact_id"]
    assert node["lineage_depth"] == 0
    assert node["lineage_type"] == "original"
    assert node["lineage_id"].startswith("repair_lineage_")


def test_replay_creates_derived_lineage():
    artifact = _committed_artifact()
    root_node = create_runtime_repair_lineage_node(artifact)
    replay_artifact = _derived_artifact(artifact, "artifact_replay_001", "replay")

    replay_node = create_runtime_repair_lineage_node(replay_artifact)

    assert replay_node["parent_artifact_id"] == root_node["artifact_id"]
    assert replay_node["root_artifact_id"] == root_node["artifact_id"]
    assert replay_node["lineage_depth"] == 1
    assert replay_node["lineage_type"] == "replay"


def test_lineage_graph_builds_correctly():
    artifact = _committed_artifact()
    root = create_runtime_repair_lineage_node(artifact)
    replay = create_runtime_repair_lineage_node(_derived_artifact(artifact, "artifact_replay_001", "replay"))
    rollback = create_runtime_repair_lineage_node(_derived_artifact(artifact, "artifact_rollback_001", "rollback"))

    graph = build_runtime_repair_lineage_graph([rollback, replay, root])

    assert graph["root_artifact_id"] == root["artifact_id"]
    assert graph["node_count"] == 3
    assert [root["artifact_id"]] in graph["lineage_paths"]
    assert [root["artifact_id"], replay["artifact_id"]] in graph["lineage_paths"]
    assert graph["replay_chain"] == [replay["artifact_id"]]
    assert graph["rollback_chain"] == [rollback["artifact_id"]]
    assert validate_runtime_repair_lineage_graph(graph)["valid"] is True


def test_lineage_graph_digest_deterministic():
    artifact = _committed_artifact()
    root = create_runtime_repair_lineage_node(artifact)
    replay = create_runtime_repair_lineage_node(_derived_artifact(artifact, "artifact_replay_001", "replay"))

    first = build_runtime_repair_lineage_graph([replay, root])
    second = build_runtime_repair_lineage_graph([root, replay])

    assert first["graph_digest"] == second["graph_digest"]


def test_lineage_cycle_detection_works():
    artifact = _committed_artifact()
    first = create_runtime_repair_lineage_node(artifact)
    second = create_runtime_repair_lineage_node(_derived_artifact(artifact, "artifact_replay_001", "replay"))
    first["parent_artifact_id"] = second["artifact_id"]
    first["immutable_fields"]["parent_artifact_id"] = second["artifact_id"]
    first["immutable_digest"] = second["immutable_digest"]

    graph = build_runtime_repair_lineage_graph([first, second])
    validation = validate_runtime_repair_lineage_graph(graph)

    assert validation["valid"] is False
    assert validation["cycle_detected"] is True
    assert "cycle_detected" in validation["issues"]


def test_lineage_orphan_detection_works():
    artifact = _committed_artifact()
    orphan = create_runtime_repair_lineage_node(_derived_artifact(artifact, "artifact_replay_001", "replay"))

    graph = build_runtime_repair_lineage_graph([orphan])
    validation = validate_runtime_repair_lineage_graph(graph)

    assert validation["valid"] is False
    assert validation["orphan_nodes"] == [orphan["artifact_id"]]
    assert "orphan_nodes" in validation["issues"]


def test_immutable_lineage_protected():
    artifact = _committed_artifact()
    node = create_runtime_repair_lineage_node(artifact)
    node["root_artifact_id"] = "tampered"

    graph = build_runtime_repair_lineage_graph([node])
    validation = validate_runtime_repair_lineage_graph(graph)

    assert validation["valid"] is False
    assert validation["immutable_ok"] is False
    assert "immutable_fields_modified" in validation["issues"]


def test_replay_ancestry_preserved():
    artifact = _committed_artifact()
    root = create_runtime_repair_lineage_node(artifact)
    replay_artifact = _derived_artifact(artifact, "artifact_replay_001", "replay")
    replay = create_runtime_repair_lineage_node(replay_artifact)

    graph = build_runtime_repair_lineage_graph([root, replay])
    validation = validate_runtime_repair_lineage_graph(graph)

    assert validation["valid"] is True
    assert [root["artifact_id"], replay["artifact_id"]] in graph["lineage_paths"]


def _knowledge_inputs():
    artifact = _committed_artifact()
    replay = replay_runtime_repair_commit_artifact(artifact)
    lineage = create_runtime_repair_lineage_node(artifact)
    return artifact, replay, lineage


def test_knowledge_snapshot_generated():
    artifact, replay, lineage = _knowledge_inputs()

    snapshot = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)

    assert snapshot["knowledge_id"].startswith("repair_knowledge_")
    assert snapshot["artifact_id"] == artifact["artifact_id"]
    assert snapshot["lineage_id"] == lineage["lineage_id"]
    assert snapshot["generated_at"]
    assert snapshot["knowledge_digest"]
    assert validate_runtime_repair_knowledge_snapshot(snapshot)["valid"] is True


def test_knowledge_repair_patterns_extracted():
    artifact, replay, lineage = _knowledge_inputs()

    snapshot = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)

    assert "write dominant" in snapshot["repair_patterns"]
    assert "replay stable" in snapshot["repair_patterns"]
    assert snapshot["operation_patterns"]["operation_count"] == 1
    assert snapshot["operation_patterns"]["file_count"] == 1
    assert snapshot["operation_patterns"]["write_ratio"] == 1
    assert snapshot["changed_file_types"] == [".py"]


def test_knowledge_rollback_patterns_extracted():
    artifact = _committed_artifact()
    artifact["rollback_performed"] = True
    artifact["commit_success"] = False
    replay = replay_runtime_repair_commit_artifact(artifact)
    replay["replay_success"] = False
    replay["replay_diff_summary"] = {
        "total_files_changed": 0,
        "writes": 0,
        "patches": 0,
        "deletes": 0,
        "failures": 1,
        "rollback": True,
    }
    replay["replay_digest"] = "rollback-digest"
    lineage = create_runtime_repair_lineage_node(artifact)

    snapshot = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)

    assert snapshot["rollback_patterns"]["rollback_occurred"] is True
    assert snapshot["rollback_patterns"]["rollback_success"] is True
    assert snapshot["rollback_patterns"]["rollback_reproducible"] is False
    assert "rollback triggered" in snapshot["repair_patterns"]


def test_knowledge_replay_consistency_tracked():
    artifact, replay, lineage = _knowledge_inputs()

    snapshot = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)

    assert snapshot["replay_consistency"] == "stable"


def test_knowledge_digest_deterministic_stable():
    artifact, replay, lineage = _knowledge_inputs()

    first = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)
    second = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)

    assert first["knowledge_digest"] == second["knowledge_digest"]
    assert first["knowledge_id"] == second["knowledge_id"]


def test_immutable_knowledge_protected():
    artifact, replay, lineage = _knowledge_inputs()
    snapshot = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)
    snapshot["artifact_id"] = "tampered"

    validation = validate_runtime_repair_knowledge_snapshot(snapshot)

    assert validation["valid"] is False
    assert validation["immutable_ok"] is False
    assert "immutable_fields_modified" in validation["issues"]


def test_knowledge_lineage_linkage_preserved():
    artifact, replay, lineage = _knowledge_inputs()

    snapshot = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)

    assert snapshot["artifact_id"] == artifact["artifact_id"]
    assert snapshot["lineage_id"] == lineage["lineage_id"]


def test_unstable_replay_marked_unstable():
    artifact, replay, lineage = _knowledge_inputs()
    replay["replay_digest"] = "tampered"

    snapshot = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)

    assert snapshot["replay_consistency"] == "unstable"
    assert "replay stable" not in snapshot["repair_patterns"]


def _knowledge_index_snapshots():
    artifact, replay, lineage = _knowledge_inputs()
    write_snapshot = build_runtime_repair_knowledge_snapshot(artifact, replay, lineage)

    patch_snapshot = dict(write_snapshot)
    patch_snapshot["knowledge_id"] = "repair_knowledge_patch"
    patch_snapshot["artifact_id"] = "artifact_patch"
    patch_snapshot["lineage_id"] = "lineage_patch"
    patch_snapshot["root_lineage_id"] = "lineage_root"
    patch_snapshot["repair_patterns"] = ["patch dominant", "replay stable"]
    patch_snapshot["operation_patterns"] = {
        "operation_count": 1,
        "file_count": 1,
        "write_ratio": 0,
        "patch_ratio": 1,
        "delete_ratio": 0,
    }
    patch_snapshot["changed_file_types"] = [".md"]
    patch_snapshot["replay_consistency"] = "stable"

    delete_snapshot = dict(write_snapshot)
    delete_snapshot["knowledge_id"] = "repair_knowledge_delete"
    delete_snapshot["artifact_id"] = "artifact_delete"
    delete_snapshot["lineage_id"] = "lineage_delete"
    delete_snapshot["root_lineage_id"] = "lineage_root"
    delete_snapshot["repair_patterns"] = ["delete involved"]
    delete_snapshot["operation_patterns"] = {
        "operation_count": 1,
        "file_count": 1,
        "write_ratio": 0,
        "patch_ratio": 0,
        "delete_ratio": 1,
    }
    delete_snapshot["changed_file_types"] = [".py"]
    delete_snapshot["replay_consistency"] = "unstable"
    return [delete_snapshot, write_snapshot, patch_snapshot]


def test_knowledge_index_builds():
    snapshots = _knowledge_index_snapshots()

    index = build_runtime_repair_knowledge_index(snapshots)

    assert index["index_id"].startswith("repair_knowledge_index_")
    assert index["snapshot_count"] == 3
    assert "write dominant" in index["by_repair_pattern"]
    assert "write_file" in index["by_operation_pattern"]
    assert ".py" in index["by_file_type"]
    assert "stable" in index["by_replay_consistency"]
    assert validate_runtime_repair_knowledge_index(index)["valid"] is True


def test_query_knowledge_index_by_repair_pattern_works():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())

    result = query_runtime_repair_knowledge_index(index, {"repair_pattern": "patch dominant"})

    assert result["match_count"] == 1
    assert result["matches"][0]["artifact_id"] == "artifact_patch"
    assert result["query_digest"]


def test_query_knowledge_index_by_operation_type_works():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())

    result = query_runtime_repair_knowledge_index(index, {"operation_type": "delete_file"})

    assert result["match_count"] == 1
    assert result["matches"][0]["artifact_id"] == "artifact_delete"


def test_query_knowledge_index_by_file_type_works():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())

    result = query_runtime_repair_knowledge_index(index, {"file_type": ".md"})

    assert result["match_count"] == 1
    assert result["matches"][0]["artifact_id"] == "artifact_patch"


def test_query_knowledge_index_by_replay_consistency_works():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())

    result = query_runtime_repair_knowledge_index(index, {"replay_consistency": "unstable"})

    assert result["match_count"] == 1
    assert result["matches"][0]["artifact_id"] == "artifact_delete"


def test_knowledge_index_digest_deterministic_stable():
    snapshots = _knowledge_index_snapshots()

    first = build_runtime_repair_knowledge_index(snapshots)
    second = build_runtime_repair_knowledge_index(list(reversed(snapshots)))

    assert first["index_digest"] == second["index_digest"]
    assert first["index_id"] == second["index_id"]


def test_knowledge_query_ordering_deterministic_stable():
    snapshots = _knowledge_index_snapshots()
    index = build_runtime_repair_knowledge_index(snapshots)
    expected = sorted([
        snapshot["artifact_id"]
        for snapshot in snapshots
        if ".py" in snapshot["changed_file_types"]
    ])

    first = query_runtime_repair_knowledge_index(index, {"file_type": ".py"})
    second = query_runtime_repair_knowledge_index(index, {"file_type": ".py"})

    assert [item["artifact_id"] for item in first["matches"]] == expected
    assert first["matches"] == second["matches"]
    assert first["query_digest"] == second["query_digest"]


def test_tampered_knowledge_index_fails_validation():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())
    index["snapshot_count"] = 999

    validation = validate_runtime_repair_knowledge_index(index)

    assert validation["valid"] is False
    assert validation["digest_ok"] is False
    assert "index_digest_mismatch" in validation["issues"]
    assert "snapshot_count_mismatch" in validation["issues"]


def test_similarity_query_builds():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/new.py",
                "content": "new\n",
            }
        ],
    }
    preview = build_runtime_repair_commit_preview(
        apply_runtime_repair_transaction_sandbox(transaction)
    )
    preview["replay_consistency"] = "stable"

    query = build_runtime_repair_similarity_query(transaction, preview)

    assert query["query_id"].startswith("repair_similarity_query_")
    assert query["repair_patterns"] == ["write dominant", "replay stable"]
    assert query["operation_patterns"]["operation_types"] == ["write_file"]
    assert query["file_types"] == [".py"]
    assert query["changed_file_count"] == 1
    assert query["replay_consistency"] == "stable"
    assert query["query_digest"]


def test_candidate_retrieval_works():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())
    query = {
        "query_digest": "query_001",
        "repair_patterns": ["patch dominant", "replay stable"],
        "operation_patterns": {
            "operation_types": ["patch_file"],
            "rollback_triggered": False,
        },
        "file_types": [".md"],
        "changed_file_count": 1,
        "replay_consistency": "stable",
    }

    result = retrieve_runtime_repair_candidates(index, query)

    assert result["retrieval_id"].startswith("repair_candidate_retrieval_")
    assert result["ranked_matches"][0]["artifact_id"] == "artifact_patch"
    assert result["similarity_scores"]["artifact_patch"] > 0
    assert validate_runtime_repair_candidate_retrieval(result)["valid"] is True


def test_candidate_ranking_deterministic():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())
    query = {
        "query_digest": "query_001",
        "repair_patterns": ["replay stable"],
        "operation_patterns": {
            "operation_types": [],
            "rollback_triggered": False,
        },
        "file_types": [],
        "changed_file_count": 1,
        "replay_consistency": "stable",
    }

    first = retrieve_runtime_repair_candidates(index, query)
    second = retrieve_runtime_repair_candidates(index, query)

    assert first["ranked_matches"] == second["ranked_matches"]
    assert first["similarity_scores"] == second["similarity_scores"]
    assert first["retrieval_digest"] == second["retrieval_digest"]


def test_similarity_scoring_stable():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())
    query = {
        "query_digest": "query_001",
        "repair_patterns": ["write dominant", "replay stable"],
        "operation_patterns": {
            "operation_types": ["write_file"],
            "rollback_triggered": False,
        },
        "file_types": [".py"],
        "changed_file_count": 1,
        "replay_consistency": "stable",
    }

    result = retrieve_runtime_repair_candidates(index, query)
    top = result["ranked_matches"][0]

    assert result["similarity_scores"][top["artifact_id"]] == 10


def test_replay_consistency_contributes_similarity_score():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())
    stable_query = {
        "query_digest": "query_stable",
        "repair_patterns": [],
        "operation_patterns": {
            "operation_types": [],
            "rollback_triggered": False,
        },
        "file_types": [],
        "changed_file_count": 0,
        "replay_consistency": "stable",
    }
    unstable_query = {
        **stable_query,
        "query_digest": "query_unstable",
        "replay_consistency": "unstable",
    }

    stable_result = retrieve_runtime_repair_candidates(index, stable_query)
    unstable_result = retrieve_runtime_repair_candidates(index, unstable_query)

    assert stable_result["similarity_scores"]["artifact_patch"] == 1
    assert unstable_result["similarity_scores"]["artifact_delete"] == 1


def test_rollback_pattern_contributes_similarity_score():
    snapshot = _knowledge_index_snapshots()[0]
    rollback_snapshot = dict(snapshot)
    rollback_snapshot["knowledge_id"] = "repair_knowledge_rollback"
    rollback_snapshot["artifact_id"] = "artifact_rollback"
    rollback_snapshot["repair_patterns"] = ["rollback triggered"]
    rollback_snapshot["operation_patterns"] = {
        "operation_count": 1,
        "file_count": 0,
        "write_ratio": 0,
        "patch_ratio": 0,
        "delete_ratio": 0,
    }
    rollback_snapshot["changed_file_types"] = []
    rollback_snapshot["replay_consistency"] = "unstable"
    index = build_runtime_repair_knowledge_index([rollback_snapshot])
    query = {
        "query_digest": "query_rollback",
        "repair_patterns": ["rollback triggered"],
        "operation_patterns": {
            "operation_types": [],
            "rollback_triggered": True,
        },
        "file_types": [],
        "changed_file_count": 0,
        "replay_consistency": "unknown",
    }

    result = retrieve_runtime_repair_candidates(index, query)

    assert result["similarity_scores"]["artifact_rollback"] == 4


def test_candidate_retrieval_digest_deterministic():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())
    query = {
        "query_digest": "query_001",
        "repair_patterns": ["write dominant"],
        "operation_patterns": {
            "operation_types": ["write_file"],
            "rollback_triggered": False,
        },
        "file_types": [".py"],
        "changed_file_count": 1,
        "replay_consistency": "stable",
    }

    first = retrieve_runtime_repair_candidates(index, query)
    second = retrieve_runtime_repair_candidates(index, query)

    assert first["retrieval_digest"] == second["retrieval_digest"]


def test_tampered_candidate_retrieval_fails_validation():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())
    query = {
        "query_digest": "query_001",
        "repair_patterns": ["replay stable"],
        "operation_patterns": {
            "operation_types": [],
            "rollback_triggered": False,
        },
        "file_types": [],
        "changed_file_count": 1,
        "replay_consistency": "stable",
    }
    result = retrieve_runtime_repair_candidates(index, query)
    result["similarity_scores"][result["ranked_matches"][0]["artifact_id"]] = -1

    validation = validate_runtime_repair_candidate_retrieval(result)

    assert validation["valid"] is False
    assert "ranking_not_deterministic" in validation["issues"]


def _candidate_retrieval_for_explanations():
    index = build_runtime_repair_knowledge_index(_knowledge_index_snapshots())
    query = {
        "query_digest": "query_001",
        "repair_patterns": ["write dominant", "replay stable"],
        "operation_patterns": {
            "operation_types": ["write_file"],
            "rollback_triggered": False,
        },
        "file_types": [".py"],
        "changed_file_count": 1,
        "replay_consistency": "stable",
    }
    return query, retrieve_runtime_repair_candidates(index, query)


def test_candidate_explanation_generated():
    query, retrieval = _candidate_retrieval_for_explanations()
    candidate = retrieval["ranked_matches"][0]

    explanation = explain_runtime_repair_candidate_match(query, candidate)

    assert explanation["candidate_id"] == candidate["artifact_id"]
    assert explanation["explanation_id"].startswith("repair_candidate_explanation_")
    assert explanation["similarity_score"] == retrieval["similarity_scores"][candidate["artifact_id"]]
    assert explanation["explanation_digest"]


def test_matched_repair_pattern_explained():
    query, retrieval = _candidate_retrieval_for_explanations()

    explanation = explain_runtime_repair_candidate_match(query, retrieval["ranked_matches"][0])

    assert "write dominant" in explanation["matched_patterns"]
    assert "matched repair pattern" in explanation["explanation_summary"]


def test_matched_file_type_explained():
    query, retrieval = _candidate_retrieval_for_explanations()

    explanation = explain_runtime_repair_candidate_match(query, retrieval["ranked_matches"][0])

    assert explanation["matched_file_types"] == [".py"]
    assert "matched file type" in explanation["explanation_summary"]


def test_replay_consistency_explained():
    query, retrieval = _candidate_retrieval_for_explanations()

    explanation = explain_runtime_repair_candidate_match(query, retrieval["ranked_matches"][0])

    assert explanation["replay_consistency_match"] is True
    assert "matched replay consistency" in explanation["explanation_summary"]


def test_rollback_pattern_explained():
    candidate = {
        "knowledge_id": "repair_knowledge_rollback",
        "artifact_id": "artifact_rollback",
        "lineage_id": "lineage_rollback",
        "repair_patterns": ["rollback triggered"],
        "operation_type_ratios": {
            "write_file": 0,
            "patch_file": 0,
            "delete_file": 0,
        },
        "changed_file_types": [],
        "replay_consistency": "unstable",
    }
    query = {
        "repair_patterns": ["rollback triggered"],
        "operation_patterns": {
            "operation_types": [],
            "rollback_triggered": True,
        },
        "file_types": [],
        "replay_consistency": "unknown",
    }

    explanation = explain_runtime_repair_candidate_match(query, candidate)

    assert explanation["rollback_pattern_match"] is True
    assert "matched rollback behavior" in explanation["explanation_summary"]


def test_candidate_explanation_digest_deterministic():
    _, retrieval = _candidate_retrieval_for_explanations()

    first = build_runtime_repair_candidate_explanations(retrieval)
    second = build_runtime_repair_candidate_explanations(retrieval)

    assert first["explanations_digest"] == second["explanations_digest"]


def test_candidate_explanation_ordering_stable():
    _, retrieval = _candidate_retrieval_for_explanations()

    result = build_runtime_repair_candidate_explanations(retrieval)

    assert result["explanations"] == sorted(
        result["explanations"],
        key=lambda item: (-item["similarity_score"], item["candidate_id"], item["explanation_id"]),
    )
    assert validate_runtime_repair_candidate_explanations(result)["valid"] is True


def test_tampered_candidate_explanation_validation_fails():
    _, retrieval = _candidate_retrieval_for_explanations()
    result = build_runtime_repair_candidate_explanations(retrieval)
    result["explanations"][0]["similarity_score"] = -1

    validation = validate_runtime_repair_candidate_explanations(result)

    assert validation["valid"] is False
    assert "explanations_digest_mismatch" in validation["issues"]


def _recommendation_inputs():
    query, retrieval = _candidate_retrieval_for_explanations()
    explanations = build_runtime_repair_candidate_explanations(retrieval)
    query = {
        **query,
        "query_id": "repair_similarity_query_test",
    }
    return query, retrieval, explanations


def test_recommendation_draft_generated():
    query, retrieval, explanations = _recommendation_inputs()

    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)

    assert draft["draft_id"].startswith("repair_recommendation_draft_")
    assert draft["query_id"] == "repair_similarity_query_test"
    assert draft["retrieval_id"] == retrieval["retrieval_id"]
    assert draft["recommendation_status"] == "draft_only"
    assert draft["recommended_candidates"]
    assert draft["explanation_refs"]
    assert draft["draft_digest"]
    assert draft["created_at"]


def test_recommendation_draft_remains_read_only():
    query, retrieval, explanations = _recommendation_inputs()

    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)
    validation = validate_runtime_repair_recommendation_draft(draft)

    assert draft["recommendation_status"] == "draft_only"
    assert validation["read_only_ok"] is True
    assert validation["valid"] is True


def test_recommendation_high_confidence_detected():
    query, retrieval, explanations = _recommendation_inputs()

    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)

    assert draft["confidence_summary"] == "high"


def test_recommendation_medium_confidence_detected():
    query, retrieval, explanations = _recommendation_inputs()
    retrieval["similarity_scores"] = {
        item["artifact_id"]: 4
        for item in retrieval["ranked_matches"]
    }

    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)

    assert draft["confidence_summary"] == "medium"


def test_recommendation_low_confidence_detected():
    query, retrieval, explanations = _recommendation_inputs()
    retrieval["ranked_matches"] = []
    retrieval["similarity_scores"] = {}

    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)

    assert draft["confidence_summary"] == "low"


def test_recommendation_limitations_included():
    query, retrieval, explanations = _recommendation_inputs()

    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)

    assert draft["limitations"] == [
        "read-only recommendation",
        "does not modify transaction",
        "requires human review before use",
    ]


def test_recommendation_draft_digest_deterministic():
    query, retrieval, explanations = _recommendation_inputs()

    first = build_runtime_repair_recommendation_draft(query, retrieval, explanations)
    second = build_runtime_repair_recommendation_draft(query, retrieval, explanations)

    assert first["draft_digest"] == second["draft_digest"]
    assert first["draft_id"] == second["draft_id"]


def test_tampered_recommendation_draft_validation_fails():
    query, retrieval, explanations = _recommendation_inputs()
    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)
    draft["recommendation_status"] = "auto_apply"

    validation = validate_runtime_repair_recommendation_draft(draft)

    assert validation["valid"] is False
    assert validation["digest_ok"] is False
    assert validation["read_only_ok"] is False
    assert "draft_digest_mismatch" in validation["issues"]
    assert "read_only_constraints_missing" in validation["issues"]


def _recommendation_draft_for_review():
    query, retrieval, explanations = _recommendation_inputs()
    return build_runtime_repair_recommendation_draft(query, retrieval, explanations)


def test_recommendation_review_generated():
    draft = _recommendation_draft_for_review()

    review = create_runtime_repair_recommendation_review(draft)

    assert review["review_id"].startswith("repair_recommendation_review_")
    assert review["draft_id"] == draft["draft_id"]
    assert review["review_status"] == "pending"
    assert review["usable"] is False
    assert review["created_at"]
    assert review["review_digest"]
    assert validate_runtime_repair_recommendation_review(review)["valid"] is True


def test_pending_recommendation_review_not_usable():
    review = create_runtime_repair_recommendation_review(_recommendation_draft_for_review())

    assert review["review_status"] == "pending"
    assert review["usable"] is False


def test_approved_recommendation_review_usable():
    review = create_runtime_repair_recommendation_review(_recommendation_draft_for_review())

    approved = approve_runtime_repair_recommendation_review(
        review,
        reviewer="human",
        note="usable as context",
    )

    assert approved["review_status"] == "approved"
    assert approved["approved_by"] == "human"
    assert approved["note"] == "usable as context"
    assert approved["usable"] is True
    assert approved["approved_at"]
    assert validate_runtime_repair_recommendation_review(approved)["valid"] is True


def test_rejected_recommendation_review_unusable():
    review = create_runtime_repair_recommendation_review(_recommendation_draft_for_review())

    rejected = reject_runtime_repair_recommendation_review(
        review,
        reviewer="human",
        reason="not relevant",
    )

    assert rejected["review_status"] == "rejected"
    assert rejected["rejected_by"] == "human"
    assert rejected["reason"] == "not relevant"
    assert rejected["usable"] is False
    assert rejected["rejected_at"]
    assert validate_runtime_repair_recommendation_review(rejected)["valid"] is True


def test_approved_recommendation_still_read_only():
    draft = _recommendation_draft_for_review()
    review = create_runtime_repair_recommendation_review(draft)

    approved = approve_runtime_repair_recommendation_review(review, "human", "ok")

    assert approved["usable"] is True
    assert validate_runtime_repair_recommendation_draft(approved["draft_snapshot"])["read_only_ok"] is True
    assert approved["draft_snapshot"]["recommendation_status"] == "draft_only"


def test_recommendation_review_digest_deterministic():
    draft = _recommendation_draft_for_review()

    first = create_runtime_repair_recommendation_review(draft)
    second = create_runtime_repair_recommendation_review(draft)

    assert first["review_digest"] == second["review_digest"]
    assert first["review_id"] == second["review_id"]


def test_tampered_recommendation_review_validation_fails():
    review = create_runtime_repair_recommendation_review(_recommendation_draft_for_review())
    review["usable"] = True

    validation = validate_runtime_repair_recommendation_review(review)

    assert validation["valid"] is False
    assert validation["deterministic_ok"] is False
    assert "usable_without_approval" in validation["issues"]
    assert "review_digest_mismatch" in validation["issues"]


def _recommendation_provenance_inputs(include_review=True):
    query, retrieval, explanations = _recommendation_inputs()
    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)
    review = None
    if include_review:
        review = approve_runtime_repair_recommendation_review(
            create_runtime_repair_recommendation_review(draft),
            reviewer="human",
            note="approved",
        )
    provenance = build_runtime_repair_recommendation_provenance(
        draft,
        retrieval,
        explanations,
        review,
    )
    return draft, retrieval, explanations, review, provenance


def test_recommendation_provenance_generated():
    draft, retrieval, explanations, review, provenance = _recommendation_provenance_inputs()

    assert provenance["provenance_id"].startswith("repair_recommendation_provenance_")
    assert provenance["recommendation_id"] == draft["draft_id"]
    assert provenance["retrieval_id"] == retrieval["retrieval_id"]
    assert provenance["explanation_ids"]
    assert provenance["candidate_artifact_ids"]
    assert provenance["created_at"]
    assert validate_runtime_repair_recommendation_provenance(provenance)["valid"] is True


def test_recommendation_provenance_lineage_refs_preserved():
    _, _, _, _, provenance = _recommendation_provenance_inputs()

    assert provenance["lineage_refs"]["candidate_lineage_ids"]
    assert "lineage_root" in provenance["lineage_refs"]["root_lineage_ids"]


def test_recommendation_provenance_replay_consistency_refs_preserved():
    _, _, _, _, provenance = _recommendation_provenance_inputs()

    assert provenance["replay_consistency_refs"]["stable_sources"]
    assert provenance["replay_consistency_refs"]["rollback_sources"] == []


def test_recommendation_provenance_review_linkage_preserved():
    _, _, _, review, provenance = _recommendation_provenance_inputs()

    assert provenance["review_id"] == review["review_id"]
    assert provenance["review_status"] == "approved"


def test_recommendation_provenance_digest_deterministic():
    draft, retrieval, explanations, review, first = _recommendation_provenance_inputs()
    second = build_runtime_repair_recommendation_provenance(
        draft,
        retrieval,
        explanations,
        review,
    )

    assert first["provenance_digest"] == second["provenance_digest"]
    assert first["provenance_id"] == second["provenance_id"]


def test_recommendation_provenance_immutable_protected():
    provenance = _recommendation_provenance_inputs()[4]

    validation = validate_runtime_repair_recommendation_provenance(provenance)

    assert validation == {
        "valid": True,
        "immutable_ok": True,
        "digest_ok": True,
        "issues": [],
    }


def test_tampered_recommendation_provenance_validation_fails():
    provenance = _recommendation_provenance_inputs()[4]
    provenance["retrieval_id"] = "tampered"

    validation = validate_runtime_repair_recommendation_provenance(provenance)

    assert validation["valid"] is False
    assert validation["immutable_ok"] is False
    assert validation["digest_ok"] is False
    assert "immutable_fields_modified" in validation["issues"]
    assert "provenance_digest_mismatch" in validation["issues"]


def test_low_risk_assessment_works():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/new.py",
                "content": "new\n",
            }
        ],
    }

    risk = assess_runtime_repair_risk(transaction)

    assert risk["risk_score"] == 0
    assert risk["risk_level"] == "low"
    assert risk["risk_factors"] == []
    assert validate_runtime_repair_risk_assessment(risk)["valid"] is True


def test_medium_risk_assessment_works():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "patch_file",
                "target_path": "project/a.py",
                "patch": "--- a/a.py\n+++ b/a.py\n+a",
            },
            {
                "op_type": "patch_file",
                "target_path": "project/b.py",
                "patch": "--- a/b.py\n+++ b/b.py\n+b",
            },
            {
                "op_type": "write_file",
                "target_path": "project/c.py",
                "content": "c\n",
            },
        ],
    }

    risk = assess_runtime_repair_risk(transaction)

    assert risk["risk_score"] == 4
    assert risk["risk_level"] == "medium"
    assert {item["factor"] for item in risk["risk_factors"]} == {"high_file_count", "patch_dominant"}


def test_high_risk_assessment_works():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "project/delete.py",
                "payload": {"confirm": True},
            }
        ],
        "repair_history": [
            {
                "rollback_performed": True,
            }
        ],
    }

    risk = assess_runtime_repair_risk(transaction)

    assert risk["risk_score"] == 7
    assert risk["risk_level"] == "high"


def test_critical_risk_assessment_works():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "project/delete.py",
                "payload": {"confirm": True},
            },
            {
                "op_type": "patch_file",
                "target_path": "project/a.py",
                "patch": "--- a/a.py\n+++ b/a.py\n+a",
            },
            {
                "op_type": "patch_file",
                "target_path": "project/b.py",
                "patch": "--- a/b.py\n+++ b/b.py\n+b",
            },
        ],
        "rollback_performed": True,
    }
    retrieval = {
        "ranked_matches": [
            {
                "artifact_id": "artifact_unstable",
                "replay_consistency": "unstable",
            }
        ]
    }
    draft = {
        "confidence_summary": "low",
    }

    risk = assess_runtime_repair_risk(transaction, draft, retrieval)

    assert risk["risk_score"] == 16
    assert risk["risk_level"] == "critical"


def test_rollback_history_increases_risk():
    transaction = {
        **_staged_transaction(),
        "operations": [],
        "rollback_performed": True,
    }

    risk = assess_runtime_repair_risk(transaction)

    assert {"factor": "rollback_history", "score": 3} in risk["risk_factors"]


def test_unstable_replay_increases_risk():
    transaction = {
        **_staged_transaction(),
        "operations": [],
    }
    retrieval = {
        "ranked_matches": [
            {
                "artifact_id": "artifact_unstable",
                "replay_consistency": "unstable",
            }
        ]
    }

    risk = assess_runtime_repair_risk(transaction, retrieval_result=retrieval)

    assert {"factor": "unstable_replay", "score": 3} in risk["risk_factors"]


def test_no_historical_match_increases_risk():
    transaction = {
        **_staged_transaction(),
        "operations": [],
    }
    retrieval = {
        "ranked_matches": [],
    }

    risk = assess_runtime_repair_risk(transaction, retrieval_result=retrieval)

    assert {"factor": "no_historical_match", "score": 3} in risk["risk_factors"]


def test_risk_digest_deterministic_stable():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "project/delete.py",
                "payload": {"confirm": True},
            }
        ],
    }

    first = assess_runtime_repair_risk(transaction)
    second = assess_runtime_repair_risk(transaction)

    assert first["risk_digest"] == second["risk_digest"]
    assert first["risk_id"] == second["risk_id"]


def test_tampered_risk_assessment_validation_fails():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "project/delete.py",
                "payload": {"confirm": True},
            }
        ],
    }
    risk = assess_runtime_repair_risk(transaction)
    risk["risk_score"] = 0

    validation = validate_runtime_repair_risk_assessment(risk)

    assert validation["valid"] is False
    assert validation["deterministic_ok"] is False
    assert "risk_not_deterministic" in validation["issues"]
    assert "risk_digest_mismatch" in validation["issues"]


def _decision_trace_inputs():
    query, retrieval, explanations = _recommendation_inputs()
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/new.py",
                "content": "new\n",
            }
        ],
    }
    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)
    risk = assess_runtime_repair_risk(transaction, draft, {})
    return transaction, retrieval, explanations, draft, risk


def test_decision_trace_generated():
    transaction, retrieval, explanations, draft, risk = _decision_trace_inputs()

    trace = build_runtime_repair_decision_trace(
        transaction,
        retrieval,
        explanations,
        draft,
        risk,
    )

    assert trace["trace_id"].startswith("repair_decision_trace_")
    assert trace["transaction_id"] == transaction["transaction_id"]
    assert trace["retrieval_refs"]["retrieval_id"] == retrieval["retrieval_id"]
    assert trace["recommendation_ref"]["recommendation_id"] == draft["draft_id"]
    assert trace["risk_ref"]["risk_id"] == risk["risk_id"]
    assert trace["final_decision_state"] == "advisory_only"
    assert trace["trace_digest"]
    assert trace["created_at"]
    assert validate_runtime_repair_decision_trace(trace)["valid"] is True


def test_decision_trace_reasoning_steps_preserved():
    trace = build_runtime_repair_decision_trace(*_decision_trace_inputs())

    assert [step["step_key"] for step in trace["reasoning_steps"]] == [
        "retrieval_matched_patterns",
        "candidate_ranking",
        "explanation_summary",
        "confidence_summary",
        "risk_factors",
        "mitigation_notes",
    ]
    assert trace["reasoning_steps"][1]["details"][0]["artifact_id"]
    assert trace["reasoning_steps"][2]["details"][0]["summary"]


def test_decision_trace_high_risk_state_detected():
    transaction, retrieval, explanations, draft, _ = _decision_trace_inputs()
    transaction = {
        **transaction,
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "project/delete.py",
                "payload": {"confirm": True},
            }
        ],
        "repair_history": [
            {
                "rollback_performed": True,
            }
        ],
    }
    risk = assess_runtime_repair_risk(transaction, draft, {})

    trace = build_runtime_repair_decision_trace(
        transaction,
        retrieval,
        explanations,
        draft,
        risk,
    )

    assert risk["risk_level"] == "high"
    assert trace["final_decision_state"] == "high_risk"


def test_decision_trace_critical_risk_state_detected():
    transaction, retrieval, explanations, draft, _ = _decision_trace_inputs()
    transaction = {
        **transaction,
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "project/delete.py",
                "payload": {"confirm": True},
            },
            {
                "op_type": "patch_file",
                "target_path": "project/a.py",
                "patch": "--- a/a.py\n+++ b/a.py\n+a",
            },
            {
                "op_type": "patch_file",
                "target_path": "project/b.py",
                "patch": "--- a/b.py\n+++ b/b.py\n+b",
            },
        ],
        "rollback_performed": True,
    }
    retrieval = {
        **retrieval,
        "ranked_matches": [
            {
                "artifact_id": "artifact_unstable",
                "replay_consistency": "unstable",
            }
        ],
    }
    draft = {
        **draft,
        "confidence_summary": "low",
    }
    risk = assess_runtime_repair_risk(transaction, draft, retrieval)

    trace = build_runtime_repair_decision_trace(
        transaction,
        retrieval,
        explanations,
        draft,
        risk,
    )

    assert risk["risk_level"] == "critical"
    assert trace["final_decision_state"] == "critical_risk"


def test_decision_trace_recommendation_linkage_preserved():
    transaction, retrieval, explanations, draft, risk = _decision_trace_inputs()
    approved_draft = {
        **draft,
        "review_status": "approved",
        "usable": True,
    }

    trace = build_runtime_repair_decision_trace(
        transaction,
        retrieval,
        explanations,
        approved_draft,
        risk,
    )

    assert trace["recommendation_ref"]["recommendation_id"] == draft["draft_id"]
    assert trace["recommendation_ref"]["review_status"] == "approved"
    assert trace["recommendation_ref"]["usable"] is True
    assert trace["final_decision_state"] == "review_required"


def test_decision_trace_digest_deterministic_stable():
    inputs = _decision_trace_inputs()

    first = build_runtime_repair_decision_trace(*inputs)
    second = build_runtime_repair_decision_trace(*inputs)

    assert first["trace_digest"] == second["trace_digest"]
    assert first["trace_id"] == second["trace_id"]


def test_tampered_decision_trace_validation_fails():
    trace = build_runtime_repair_decision_trace(*_decision_trace_inputs())
    trace["reasoning_steps"][0]["step_key"] = "tampered"

    validation = validate_runtime_repair_decision_trace(trace)

    assert validation["valid"] is False
    assert validation["deterministic_ok"] is False
    assert "reasoning_order_not_deterministic" in validation["issues"]
    assert "trace_digest_mismatch" in validation["issues"]


def _policy_allowed_inputs():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/new.py",
                "content": "new\n",
            }
        ],
    }
    recommendation = {
        "draft_id": "repair_recommendation_draft_policy_allowed",
        "replay_consistency": "stable",
    }
    risk = assess_runtime_repair_risk(transaction, recommendation, {})
    return transaction, recommendation, risk


def test_allowed_policy_evaluation_works():
    transaction, recommendation, risk = _policy_allowed_inputs()

    result = evaluate_runtime_repair_policy(transaction, recommendation, risk)

    assert result["policy_eval_id"].startswith("repair_policy_eval_")
    assert result["transaction_id"] == transaction["transaction_id"]
    assert result["policy_result"] == "allowed"
    assert result["violated_policies"] == []
    assert result["warnings"] == []
    assert result["enforcement_state"] == "advisory_only"
    assert result["evaluated_at"]
    assert validate_runtime_repair_policy_evaluation(result)["valid"] is True


def test_warning_policy_evaluation_works():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "patch_file",
                "target_path": "project/a.py",
                "patch": "--- a/a.py\n+++ b/a.py\n+a",
            },
            {
                "op_type": "patch_file",
                "target_path": "project/b.py",
                "patch": "--- a/b.py\n+++ b/b.py\n+b",
            },
            {
                "op_type": "write_file",
                "target_path": "project/c.py",
                "content": "c\n",
            },
        ],
    }
    risk = assess_runtime_repair_risk(transaction, retrieval_result={"ranked_matches": []})

    result = evaluate_runtime_repair_policy(transaction, {}, risk)

    assert result["policy_result"] == "warning"
    assert result["enforcement_state"] == "manual_review_required"
    assert "missing_replay_verification" in result["warnings"]
    assert "no_historical_match_medium_or_high_risk" in result["warnings"]
    assert result["violated_policies"] == []


def test_blocked_policy_evaluation_works():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "project/delete.py",
                "payload": {"confirm": True},
            },
            {
                "op_type": "patch_file",
                "target_path": "project/a.py",
                "patch": "--- a/a.py\n+++ b/a.py\n+a",
            },
            {
                "op_type": "patch_file",
                "target_path": "project/b.py",
                "patch": "--- a/b.py\n+++ b/b.py\n+b",
            },
        ],
        "rollback_performed": True,
    }
    risk = assess_runtime_repair_risk(
        transaction,
        {"confidence_summary": "low"},
        {
            "ranked_matches": [
                {
                    "artifact_id": "artifact_unstable",
                    "replay_consistency": "unstable",
                }
            ]
        },
    )

    result = evaluate_runtime_repair_policy(transaction, {"replay_consistency": "unstable"}, risk)

    assert result["policy_result"] == "blocked"
    assert result["enforcement_state"] == "execution_blocked"
    assert result["violated_policies"] == ["critical_delete_file_blocked"]


def test_policy_critical_delete_blocked():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "project/delete.py",
                "payload": {"confirm": True},
            }
        ],
    }
    risk = {
        "risk_level": "critical",
        "risk_factors": [],
    }

    result = evaluate_runtime_repair_policy(transaction, {"replay_consistency": "stable"}, risk)

    assert result["policy_result"] == "blocked"
    assert result["violated_policies"] == ["critical_delete_file_blocked"]


def test_policy_unstable_replay_blocked():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "patch_file",
                "target_path": "project/a.py",
                "patch": "--- a/a.py\n+++ b/a.py\n+a",
            }
        ],
    }
    risk = {
        "risk_level": "high",
        "risk_factors": [
            {
                "factor": "unstable_replay",
                "score": 3,
            }
        ],
    }

    result = evaluate_runtime_repair_policy(transaction, {}, risk)

    assert result["policy_result"] == "blocked"
    assert result["violated_policies"] == ["unstable_replay_high_risk_blocked"]


def test_policy_missing_replay_verification_warning():
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/new.py",
                "content": "new\n",
            }
        ],
    }
    risk = assess_runtime_repair_risk(transaction)

    result = evaluate_runtime_repair_policy(transaction, {}, risk)

    assert result["policy_result"] == "warning"
    assert result["warnings"] == ["missing_replay_verification"]
    assert result["enforcement_state"] == "manual_review_required"


def test_policy_digest_deterministic_stable():
    inputs = _policy_allowed_inputs()

    first = evaluate_runtime_repair_policy(*inputs)
    second = evaluate_runtime_repair_policy(*inputs)

    assert first["policy_digest"] == second["policy_digest"]
    assert first["policy_eval_id"] == second["policy_eval_id"]


def test_tampered_policy_evaluation_validation_fails():
    result = evaluate_runtime_repair_policy(*_policy_allowed_inputs())
    result["warnings"] = ["z_warning", "a_warning"]

    validation = validate_runtime_repair_policy_evaluation(result)

    assert validation["valid"] is False
    assert validation["deterministic_ok"] is False
    assert "policy_ordering_not_deterministic" in validation["issues"]
    assert "policy_result_mismatch" in validation["issues"]
    assert "policy_digest_mismatch" in validation["issues"]


def _governance_report_inputs():
    query, retrieval, explanations = _recommendation_inputs()
    transaction = {
        **_staged_transaction(),
        "operations": [
            {
                "op_type": "write_file",
                "target_path": "project/new.py",
                "content": "new\n",
            }
        ],
    }
    draft = build_runtime_repair_recommendation_draft(query, retrieval, explanations)
    review = approve_runtime_repair_recommendation_review(
        create_runtime_repair_recommendation_review(draft),
        reviewer="human",
        note="approved",
    )
    provenance = build_runtime_repair_recommendation_provenance(
        draft,
        retrieval,
        explanations,
        review,
    )
    risk = assess_runtime_repair_risk(transaction, draft, {})
    trace = build_runtime_repair_decision_trace(
        transaction,
        retrieval,
        explanations,
        draft,
        risk,
    )
    policy = evaluate_runtime_repair_policy(
        transaction,
        {
            **draft,
            "replay_consistency": "stable",
        },
        risk,
    )
    return transaction, draft, review, provenance, risk, trace, policy


def test_governance_report_generated():
    inputs = _governance_report_inputs()

    report = build_runtime_repair_governance_report(*inputs)

    assert report["report_id"].startswith("repair_governance_report_")
    assert report["transaction_id"] == inputs[0]["transaction_id"]
    assert report["governance_state"] == "advisory_only"
    assert report["enforcement_state"] == "advisory_only"
    assert report["report_digest"]
    assert report["created_at"]
    assert validate_runtime_repair_governance_report(report)["valid"] is True


def test_governance_execution_blocked_state_works():
    transaction, draft, review, provenance, _, trace, _ = _governance_report_inputs()
    transaction = {
        **transaction,
        "operations": [
            {
                "op_type": "delete_file",
                "target_path": "project/delete.py",
                "payload": {"confirm": True},
            }
        ],
    }
    risk = {
        "risk_id": "repair_risk_policy_blocked",
        "risk_level": "critical",
        "risk_score": 9,
        "risk_factors": [],
    }
    policy = evaluate_runtime_repair_policy(transaction, {"replay_consistency": "stable"}, risk)

    report = build_runtime_repair_governance_report(
        transaction,
        draft,
        review,
        provenance,
        risk,
        trace,
        policy,
    )

    assert report["governance_state"] == "execution_blocked"
    assert report["enforcement_state"] == "execution_blocked"


def test_governance_high_risk_review_state_works():
    transaction, draft, review, provenance, _, trace, _ = _governance_report_inputs()
    risk = {
        "risk_id": "repair_risk_critical_without_policy_block",
        "risk_level": "critical",
        "risk_score": 9,
        "risk_factors": [
            {
                "factor": "low_similarity_confidence",
                "score": 2,
            }
        ],
    }
    policy = {
        "policy_eval_id": "repair_policy_eval_warning",
        "policy_result": "warning",
        "violated_policies": [],
        "warnings": ["missing_replay_verification"],
        "enforcement_state": "manual_review_required",
    }

    report = build_runtime_repair_governance_report(
        transaction,
        draft,
        review,
        provenance,
        risk,
        trace,
        policy,
    )

    assert report["governance_state"] == "high_risk_review"
    assert report["enforcement_state"] == "manual_review_required"


def test_governance_recommendation_summary_included():
    report = build_runtime_repair_governance_report(*_governance_report_inputs())

    assert report["recommendation_summary"]["confidence_summary"] == "high"
    assert report["recommendation_summary"]["top_candidates"]
    assert report["recommendation_summary"]["review_status"] == "approved"


def test_governance_policy_summary_included():
    inputs = _governance_report_inputs()
    report = build_runtime_repair_governance_report(*inputs)

    assert report["policy_summary"]["policy_eval_id"] == inputs[6]["policy_eval_id"]
    assert report["policy_summary"]["policy_result"] == "allowed"
    assert report["policy_summary"]["violated_policies"] == []


def test_governance_reasoning_summary_included():
    inputs = _governance_report_inputs()
    report = build_runtime_repair_governance_report(*inputs)

    assert report["reasoning_summary"]["trace_id"] == inputs[5]["trace_id"]
    assert [step["step_key"] for step in report["reasoning_summary"]["reasoning_steps"]] == [
        "retrieval_matched_patterns",
        "candidate_ranking",
        "explanation_summary",
        "confidence_summary",
        "risk_factors",
        "mitigation_notes",
    ]


def test_governance_provenance_summary_included():
    inputs = _governance_report_inputs()
    report = build_runtime_repair_governance_report(*inputs)

    assert report["provenance_summary"]["provenance_id"] == inputs[3]["provenance_id"]
    assert report["provenance_summary"]["candidate_artifact_ids"]
    assert report["provenance_summary"]["lineage_refs"]["candidate_lineage_ids"]


def test_governance_report_digest_deterministic_stable():
    inputs = _governance_report_inputs()

    first = build_runtime_repair_governance_report(*inputs)
    second = build_runtime_repair_governance_report(*inputs)

    assert first["report_digest"] == second["report_digest"]
    assert first["report_id"] == second["report_id"]


def test_tampered_governance_report_validation_fails():
    report = build_runtime_repair_governance_report(*_governance_report_inputs())
    report["policy_summary"]["violated_policies"] = ["z_policy", "a_policy"]

    validation = validate_runtime_repair_governance_report(report)

    assert validation["valid"] is False
    assert validation["deterministic_ok"] is False
    assert "summary_ordering_not_deterministic" in validation["issues"]
    assert "report_digest_mismatch" in validation["issues"]
