from __future__ import annotations

from core.runtime.task_runtime import TaskRuntime


def _runtime(tmp_path):
    return TaskRuntime(workspace_root=str(tmp_path / "workspace"))


def _record(transaction_id: str = "tx-replay-v2", gate_state: str = "approved") -> dict:
    lifecycle_stage = {
        "pending": "creation",
        "reviewed": "review",
        "verified": "verification",
        "approved": "approval",
        "commit_ready": "commit",
        "committed": "commit",
        "rolled_back": "rollback",
        "rejected": "rejection",
    }.get(gate_state, "unknown")
    return {
        "record_type": "runtime_transaction",
        "transaction_context": {"transaction_id": transaction_id},
        "path": "core/runtime/task_runtime.py",
        "domain": "repo_source",
        "scope": "repo_source",
        "gate_state": gate_state,
        "lifecycle_stage": lifecycle_stage,
        "lifecycle_flags": {
            "can_commit": gate_state in {"approved", "commit_ready"},
            "can_rollback": gate_state in {"pending", "reviewed", "verified", "approved", "commit_ready", "committed"},
        },
        "ownership": {"initiator": "runtime", "approver": "review"},
        "ownership_validation": {"required": ["initiator", "approver"], "missing": [], "valid": True},
        "execution_review": {"reviewed": True, "approved": True, "commit_ready": gate_state == "commit_ready"},
        "execution_review_validation": {"required": ["reviewed", "approved"], "missing": [], "valid": True},
        "governed_mutation": True,
        "can_commit": gate_state in {"approved", "commit_ready"},
        "can_rollback": gate_state in {"pending", "reviewed", "verified", "approved", "commit_ready", "committed"},
        "created_at": "test",
    }


def _complete_commit_evidence():
    return ["transaction_record", "mutation_context", "verification_result", "commit_target"]


def _assert_gateway_never_allows_execution(preview: dict) -> None:
    assert preview["mutation_allowed"] is False
    assert preview["executor_dispatch_allowed"] is False
    assert preview["auto_commit"] is False
    assert preview["auto_rollback"] is False
    contract = preview["execution_contract"]
    assert contract["execution_allowed"] is False
    assert contract["executor_dispatch_allowed"] is False
    assert contract["scheduler_dispatch_allowed"] is False
    assert contract["mutation_allowed"] is False
    assert contract["command_execution_allowed"] is False
    commit_preview = preview["commit_request_preview"]
    assert commit_preview["mutation_allowed"] is False
    assert commit_preview["executor_dispatch_allowed"] is False
    assert commit_preview["auto_commit"] is False
    assert commit_preview["auto_rollback"] is False


def _assert_approval_gate_never_allows_execution(gate: dict) -> None:
    assert gate["approval_granted"] is False
    assert gate["execution_allowed"] is False
    assert gate["mutation_allowed"] is False
    assert gate["executor_dispatch_allowed"] is False
    assert gate["scheduler_dispatch_allowed"] is False
    assert gate["command_execution_allowed"] is False
    assert gate["auto_commit"] is False
    assert gate["auto_rollback"] is False


def _assert_dispatch_preview_never_allows_execution(preview: dict) -> None:
    assert preview["dispatch_eligible"] is False
    assert preview["execution_allowed"] is False
    assert preview["mutation_allowed"] is False
    assert preview["executor_dispatch_allowed"] is False
    assert preview["scheduler_dispatch_allowed"] is False
    assert preview["command_execution_allowed"] is False
    assert preview["auto_commit"] is False
    assert preview["auto_rollback"] is False
    envelope = preview["execution_envelope"]
    assert envelope["execution_allowed"] is False
    assert envelope["dispatch_eligible"] is False
    assert envelope["executor_dispatch_allowed"] is False
    assert envelope["scheduler_dispatch_allowed"] is False
    assert envelope["command_execution_allowed"] is False
    assert envelope["mutation_allowed"] is False
    assert envelope["auto_commit"] is False
    assert envelope["auto_rollback"] is False


def _assert_authorization_never_allows_execution(authorization: dict) -> None:
    assert authorization["authorization_granted"] is False
    assert authorization["sandbox_eligible"] is False
    assert authorization["execution_allowed"] is False
    assert authorization["mutation_allowed"] is False
    assert authorization["executor_dispatch_allowed"] is False
    assert authorization["scheduler_dispatch_allowed"] is False
    assert authorization["command_execution_allowed"] is False
    assert authorization["auto_commit"] is False
    assert authorization["auto_rollback"] is False
    sandbox = authorization["sandbox_preview"]
    assert sandbox["sandbox_eligible"] is False
    assert sandbox["sandbox_execution_allowed"] is False
    assert sandbox["executor_dispatch_allowed"] is False
    assert sandbox["scheduler_dispatch_allowed"] is False
    assert sandbox["command_execution_allowed"] is False
    assert sandbox["mutation_allowed"] is False
    ticket = authorization["execution_ticket"]
    assert ticket["authorization_granted"] is False
    assert ticket["execution_allowed"] is False
    assert ticket["dispatch_eligible"] is False
    assert ticket["sandbox_eligible"] is False


def _assert_immutable_journal_never_allows_execution_or_write(preview: dict) -> None:
    entry = preview["journal_entry_preview"]
    assert entry["write_allowed"] is False
    assert entry["append_allowed"] is False
    assert entry["persist_allowed"] is False
    assert preview["authorization_granted"] is False
    assert preview["execution_allowed"] is False
    assert preview["mutation_allowed"] is False
    assert preview["executor_dispatch_allowed"] is False
    assert preview["scheduler_dispatch_allowed"] is False
    assert preview["command_execution_allowed"] is False
    assert preview["auto_commit"] is False
    assert preview["auto_rollback"] is False


def _assert_snapshot_never_allows_execution_or_write(snapshot: dict) -> None:
    preview = snapshot["snapshot_preview"]
    flags = snapshot["governance_flags"]
    assert preview["write_allowed"] is False
    assert preview["persist_allowed"] is False
    assert preview["append_allowed"] is False
    assert flags["write_allowed"] is False
    assert flags["persist_allowed"] is False
    assert flags["append_allowed"] is False
    assert snapshot["authorization_granted"] is False
    assert snapshot["execution_allowed"] is False
    assert snapshot["mutation_allowed"] is False
    assert snapshot["executor_dispatch_allowed"] is False
    assert snapshot["scheduler_dispatch_allowed"] is False
    assert snapshot["command_execution_allowed"] is False
    assert snapshot["auto_commit"] is False
    assert snapshot["auto_rollback"] is False


def _assert_diff_verification_never_allows_execution(result: dict) -> None:
    assert result["authorization_granted"] is False
    assert result["execution_allowed"] is False
    assert result["mutation_allowed"] is False
    assert result["executor_dispatch_allowed"] is False
    assert result["scheduler_dispatch_allowed"] is False
    assert result["command_execution_allowed"] is False
    assert result["auto_commit"] is False
    assert result["auto_rollback"] is False


def _assert_policy_resolution_never_allows_execution(result: dict) -> None:
    assert result["authorization_granted"] is False
    assert result["execution_allowed"] is False
    assert result["mutation_allowed"] is False
    assert result["executor_dispatch_allowed"] is False
    assert result["scheduler_dispatch_allowed"] is False
    assert result["command_execution_allowed"] is False
    assert result["auto_commit"] is False
    assert result["auto_rollback"] is False
    decision = result["policy_decision"]
    assert decision["execution_allowed"] is False
    assert decision["mutation_allowed"] is False
    assert decision["authorization_granted"] is False


def _approval_and_gateway(runtime: TaskRuntime, transaction_id: str, available_evidence):
    runtime._write_runtime_transaction_record(_record(transaction_id, "approved"))
    decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            transaction_id,
            available_evidence=available_evidence,
            replay_id=f"replay-{transaction_id}",
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)
    approval = runtime.build_governed_replay_approval_gate(gateway)
    return approval, gateway, decision


def _dispatch_preview(runtime: TaskRuntime, transaction_id: str, available_evidence):
    approval, gateway, decision = _approval_and_gateway(runtime, transaction_id, available_evidence)
    return runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway), approval, gateway, decision


def _authorization_preview(runtime: TaskRuntime, transaction_id: str, available_evidence):
    dispatch, approval, gateway, decision = _dispatch_preview(runtime, transaction_id, available_evidence)
    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)
    return authorization, dispatch, approval, gateway, decision


def _immutable_journal_preview(runtime: TaskRuntime, transaction_id: str, available_evidence):
    authorization, dispatch, approval, gateway, decision = _authorization_preview(runtime, transaction_id, available_evidence)
    journal = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )
    return journal, authorization, dispatch, approval, gateway, decision


def _governance_snapshot(runtime: TaskRuntime, transaction_id: str, available_evidence):
    journal, *_ = _immutable_journal_preview(runtime, transaction_id, available_evidence)
    return runtime.build_governed_replay_governance_state_snapshot(journal)


def _stable_diff_verification(runtime: TaskRuntime, transaction_id: str):
    snapshot = _governance_snapshot(runtime, transaction_id, _complete_commit_evidence())
    return runtime.build_governed_replay_governance_state_diff_verification(snapshot)


def test_replay_preflight_executable_when_evidence_complete(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-complete", "approved"))

    preflight = runtime._runtime_replay_execution_preflight(
        "tx-complete",
        available_evidence=["transaction_record", "mutation_context", "verification_result", "commit_target"],
    )

    assert preflight["status"] == "executable"
    assert preflight["is_executable"] is True
    assert preflight["missing_evidence"] == []
    assert preflight["blocked_reason"] == ""
    assert preflight["action"] == "commit"


def test_replay_preflight_blocks_missing_evidence(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-missing-evidence", "approved"))

    preflight = runtime._runtime_replay_execution_preflight(
        "tx-missing-evidence",
        available_evidence=["transaction_record"],
    )
    decision = runtime.build_replay_execution_decision(preflight)

    assert preflight["status"] == "blocked"
    assert preflight["is_executable"] is False
    assert "mutation_context" in preflight["missing_evidence"]
    assert decision["decision_type"] == "blocked_missing_evidence"


def test_replay_decision_blocks_unknown_action(tmp_path):
    runtime = _runtime(tmp_path)
    replay_request = {
        "transaction_id": "tx-unknown-action",
        "replay_action": "unknown",
        "required_evidence": ["transaction_record"],
        "terminal": False,
        "blocked": False,
    }
    preflight = runtime._build_replay_execution_preflight(
        replay_request,
        available_evidence=["transaction_record"],
        recovery_summary={"transaction_id": "tx-unknown-action", "record_found": True},
    )

    decision = runtime.build_replay_execution_decision(preflight)

    assert decision["decision_type"] == "blocked_unknown_action"
    assert decision["is_executable"] is False
    assert decision["debug_context"]["decision_type"] == "blocked_unknown_action"


def test_replay_decision_blocks_missing_transaction(tmp_path):
    runtime = _runtime(tmp_path)

    preflight = runtime._runtime_replay_execution_preflight(
        "tx-does-not-exist",
        available_evidence=["transaction_record"],
    )
    decision = runtime.build_replay_execution_decision(preflight)

    assert decision["decision_type"] == "blocked_missing_transaction"
    assert decision["is_executable"] is False
    assert decision["blocked_reason"] == "missing transaction record"


def test_replay_decision_blocks_terminal_recovery(tmp_path):
    runtime = _runtime(tmp_path)
    replay_request = {
        "transaction_id": "tx-terminal",
        "replay_action": "commit",
        "required_evidence": ["transaction_record", "mutation_context", "verification_result", "commit_target"],
        "terminal": False,
        "blocked": False,
    }
    evidence = ["transaction_record", "mutation_context", "verification_result", "commit_target"]

    for status in ("finished", "failed", "cancelled", "blocked", "terminal"):
        preflight = runtime._build_replay_execution_preflight(
            replay_request,
            available_evidence=evidence,
            recovery_summary={"transaction_id": "tx-terminal", "record_found": True, "status": status},
            replay_id=f"replay-{status}",
        )
        decision = runtime.build_replay_execution_decision(preflight)

        assert decision["decision_type"] == "blocked_terminal_recovery"
        assert decision["is_executable"] is False


def test_replay_commit_request_preview_never_allows_mutation(tmp_path):
    runtime = _runtime(tmp_path)
    decision = {
        "decision_type": "executable",
        "transaction_id": "tx-preview",
        "replay_id": "replay-preview",
        "action": "commit",
        "required_evidence": ["transaction_record"],
        "missing_evidence": [],
    }

    preview = runtime.build_replay_commit_request_preview(decision)

    assert preview["preview_only"] is True
    assert preview["mutation_allowed"] is False
    assert preview["auto_commit"] is False
    assert preview["auto_rollback"] is False
    assert preview["executor_dispatch_allowed"] is False


def test_replay_debug_context_contains_decision_fields(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-debug", "approved"))

    preflight = runtime._runtime_replay_execution_preflight(
        "tx-debug",
        available_evidence=["transaction_record"],
        replay_id="replay-debug",
    )
    decision = runtime.build_replay_execution_decision(preflight)
    debug = decision["debug_context"]

    assert debug["source"] == "runtime_replay_execution_bridge_v2"
    assert debug["transaction_id"] == "tx-debug"
    assert debug["replay_id"] == "replay-debug"
    assert debug["action"] == "commit"
    assert debug["decision_type"] == "blocked_missing_evidence"
    assert "mutation_context" in debug["missing_evidence"]
    assert "transaction_record" in debug["required_evidence"]
    assert debug["available_evidence"] == ["transaction_record"]
    assert debug["blocked_reason"]


def test_persisted_replay_recovery_roundtrip_builds_same_decision(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-roundtrip", "approved"))

    replay_request = runtime._runtime_replay_request("tx-roundtrip")
    evidence = replay_request["required_evidence"]
    preflight = runtime._runtime_replay_execution_preflight("tx-roundtrip", available_evidence=evidence)
    decision = runtime.build_replay_execution_decision(preflight)

    reloaded_runtime = _runtime(tmp_path)
    reloaded_request = reloaded_runtime._runtime_replay_request("tx-roundtrip")
    reloaded_preflight = reloaded_runtime._runtime_replay_execution_preflight("tx-roundtrip", available_evidence=evidence)
    reloaded_decision = reloaded_runtime.build_replay_execution_decision(reloaded_preflight)

    assert replay_request["replay_action"] == reloaded_request["replay_action"] == "commit"
    assert decision["decision_type"] == reloaded_decision["decision_type"] == "executable"
    assert decision["is_executable"] is reloaded_decision["is_executable"] is True
    assert decision["missing_evidence"] == reloaded_decision["missing_evidence"] == []


def test_governed_gateway_preview_ready_for_executable_decision(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-gateway-ready", "approved"))
    preflight = runtime._runtime_replay_execution_preflight(
        "tx-gateway-ready",
        available_evidence=_complete_commit_evidence(),
        replay_id="replay-ready",
    )
    decision = runtime.build_replay_execution_decision(preflight)

    preview = runtime.build_governed_replay_execution_gateway_preview(decision)

    assert preview["source"] == "governed_replay_execution_gateway_v1"
    assert preview["gateway_status"] == "preview_ready"
    assert preview["policy_gate_status"] == "review_required"
    assert preview["decision_type"] == "executable"
    assert preview["execution_contract"]["requires_human_approval"] is True
    _assert_gateway_never_allows_execution(preview)


def test_governed_gateway_blocks_missing_evidence_decision(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-gateway-missing", "approved"))
    preflight = runtime._runtime_replay_execution_preflight(
        "tx-gateway-missing",
        available_evidence=["transaction_record"],
    )
    decision = runtime.build_replay_execution_decision(preflight)

    preview = runtime.build_governed_replay_execution_gateway_preview(decision)

    assert decision["decision_type"] == "blocked_missing_evidence"
    assert preview["gateway_status"] == "blocked"
    assert preview["policy_gate_status"] == "blocked"
    assert "mutation_context" in preview["evidence_contract"]["missing_evidence"]
    _assert_gateway_never_allows_execution(preview)


def test_governed_gateway_blocks_unknown_action_decision(tmp_path):
    runtime = _runtime(tmp_path)
    decision = runtime.build_replay_execution_decision(
        runtime._build_replay_execution_preflight(
            {
                "transaction_id": "tx-gateway-unknown",
                "replay_action": "unknown",
                "required_evidence": ["transaction_record"],
            },
            available_evidence=["transaction_record"],
            recovery_summary={"transaction_id": "tx-gateway-unknown", "record_found": True},
        )
    )

    preview = runtime.build_governed_replay_execution_gateway_preview(decision)

    assert decision["decision_type"] == "blocked_unknown_action"
    assert preview["gateway_status"] == "blocked"
    assert preview["policy_gate_status"] == "blocked"
    _assert_gateway_never_allows_execution(preview)


def test_governed_gateway_blocks_terminal_recovery_decision(tmp_path):
    runtime = _runtime(tmp_path)
    decision = runtime.build_replay_execution_decision(
        runtime._build_replay_execution_preflight(
            {
                "transaction_id": "tx-gateway-terminal",
                "replay_action": "commit",
                "required_evidence": _complete_commit_evidence(),
            },
            available_evidence=_complete_commit_evidence(),
            recovery_summary={"transaction_id": "tx-gateway-terminal", "record_found": True, "status": "finished"},
        )
    )

    preview = runtime.build_governed_replay_execution_gateway_preview(decision)

    assert decision["decision_type"] == "blocked_terminal_recovery"
    assert preview["gateway_status"] == "blocked"
    assert preview["policy_gate_status"] == "blocked"
    assert preview["execution_contract"]["execution_allowed"] is False
    _assert_gateway_never_allows_execution(preview)


def test_governed_gateway_execution_contract_never_allows_dispatch(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-gateway-contract", "approved"))
    decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            "tx-gateway-contract",
            available_evidence=_complete_commit_evidence(),
        )
    )

    preview = runtime.build_governed_replay_execution_gateway_preview(decision)

    assert preview["execution_contract"]["preview_only"] is True
    assert preview["execution_contract"]["requires_human_approval"] is True
    _assert_gateway_never_allows_execution(preview)


def test_governed_gateway_evidence_contract_reflects_preflight(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-gateway-evidence", "approved"))
    preflight = runtime._runtime_replay_execution_preflight(
        "tx-gateway-evidence",
        available_evidence=["transaction_record", "mutation_context"],
    )
    decision = runtime.build_replay_execution_decision(preflight)

    preview = runtime.build_governed_replay_execution_gateway_preview(decision)
    evidence = preview["evidence_contract"]

    assert evidence["required_evidence"] == preflight["required_evidence"]
    assert evidence["available_evidence"] == preflight["available_evidence"]
    assert evidence["missing_evidence"] == preflight["missing_evidence"]
    assert evidence["evidence_complete"] is False
    assert evidence["decision_type"] == "blocked_missing_evidence"


def test_governed_gateway_debug_context_contains_policy_fields(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-gateway-debug", "approved"))
    decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            "tx-gateway-debug",
            available_evidence=["transaction_record"],
            replay_id="replay-gateway-debug",
        )
    )

    preview = runtime.build_governed_replay_execution_gateway_preview(decision)
    debug = preview["debug_context"]

    assert debug["source"] == "governed_replay_execution_gateway_v1"
    assert debug["replay_id"] == "replay-gateway-debug"
    assert debug["transaction_id"] == "tx-gateway-debug"
    assert debug["action"] == "commit"
    assert debug["decision_type"] == "blocked_missing_evidence"
    assert debug["gateway_status"] == "blocked"
    assert debug["policy_gate_status"] == "blocked"
    assert debug["blocked_reason"]
    assert debug["mutation_allowed"] is False
    assert debug["executor_dispatch_allowed"] is False
    assert debug["auto_commit"] is False
    assert debug["auto_rollback"] is False


def test_approval_gate_requires_review_for_preview_ready_gateway(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-approval-ready", "approved"))
    decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            "tx-approval-ready",
            available_evidence=_complete_commit_evidence(),
            replay_id="replay-approval-ready",
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)

    gate = runtime.build_governed_replay_approval_gate(gateway)

    assert gateway["gateway_status"] == "preview_ready"
    assert gate["source"] == "governed_replay_approval_gate_v1"
    assert gate["approval_status"] == "review_required"
    assert gate["approval_required"] is True
    _assert_approval_gate_never_allows_execution(gate)


def test_approval_gate_blocks_blocked_gateway(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-approval-blocked", "approved"))
    decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            "tx-approval-blocked",
            available_evidence=["transaction_record"],
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)

    gate = runtime.build_governed_replay_approval_gate(gateway)

    assert gateway["gateway_status"] == "blocked"
    assert gate["approval_status"] == "blocked"
    assert gate["approval_required"] is True
    _assert_approval_gate_never_allows_execution(gate)


def test_approval_gate_never_grants_approval_in_v1(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-approval-never", "approved"))
    executable_decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            "tx-approval-never",
            available_evidence=_complete_commit_evidence(),
        )
    )
    blocked_decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            "tx-approval-never",
            available_evidence=["transaction_record"],
        )
    )

    for decision in (executable_decision, blocked_decision):
        gate = runtime.build_governed_replay_approval_gate(
            runtime.build_governed_replay_execution_gateway_preview(decision)
        )
        assert gate["approval_granted"] is False
        assert gate["execution_allowed"] is False


def test_approval_gate_never_allows_execution_or_mutation(tmp_path):
    runtime = _runtime(tmp_path)
    decision = runtime.build_replay_execution_decision(
        runtime._build_replay_execution_preflight(
            {
                "transaction_id": "tx-approval-flags",
                "replay_action": "commit",
                "required_evidence": _complete_commit_evidence(),
            },
            available_evidence=_complete_commit_evidence(),
            recovery_summary={"transaction_id": "tx-approval-flags", "record_found": True},
        )
    )

    gate = runtime.build_governed_replay_approval_gate(
        runtime.build_governed_replay_execution_gateway_preview(decision)
    )

    _assert_approval_gate_never_allows_execution(gate)


def test_approval_gate_debug_context_contains_approval_fields(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-approval-debug", "approved"))
    decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            "tx-approval-debug",
            available_evidence=_complete_commit_evidence(),
            replay_id="replay-approval-debug",
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)

    gate = runtime.build_governed_replay_approval_gate(gateway)
    debug = gate["debug_context"]

    assert debug["source"] == "governed_replay_approval_gate_v1"
    assert debug["replay_id"] == "replay-approval-debug"
    assert debug["transaction_id"] == "tx-approval-debug"
    assert debug["action"] == "commit"
    assert debug["gateway_status"] == "preview_ready"
    assert debug["policy_gate_status"] == "review_required"
    assert debug["approval_status"] == "review_required"
    assert debug["approval_required"] is True
    assert debug["approval_granted"] is False
    assert debug["execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["executor_dispatch_allowed"] is False
    assert debug["scheduler_dispatch_allowed"] is False
    assert debug["command_execution_allowed"] is False
    assert debug["auto_commit"] is False
    assert debug["auto_rollback"] is False
    assert debug["decision_type"] == "executable"
    assert debug["risk_level"] == "high"


def test_approval_gate_preserves_blocked_reason(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-approval-reason", "approved"))
    decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            "tx-approval-reason",
            available_evidence=["transaction_record"],
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)

    gate = runtime.build_governed_replay_approval_gate(gateway)

    assert gate["blocked_reason"] == decision["blocked_reason"]
    assert gate["debug_context"]["blocked_reason"] == decision["blocked_reason"]


def test_approval_gate_does_not_unblock_missing_evidence(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._write_runtime_transaction_record(_record("tx-approval-missing", "approved"))
    decision = runtime.build_replay_execution_decision(
        runtime._runtime_replay_execution_preflight(
            "tx-approval-missing",
            available_evidence=["transaction_record"],
        )
    )

    gate = runtime.build_governed_replay_approval_gate(
        runtime.build_governed_replay_execution_gateway_preview(decision)
    )

    assert decision["decision_type"] == "blocked_missing_evidence"
    assert gate["approval_status"] == "blocked"
    assert gate["approval_granted"] is False
    _assert_approval_gate_never_allows_execution(gate)


def test_approval_gate_does_not_unblock_terminal_recovery(tmp_path):
    runtime = _runtime(tmp_path)
    decision = runtime.build_replay_execution_decision(
        runtime._build_replay_execution_preflight(
            {
                "transaction_id": "tx-approval-terminal",
                "replay_action": "commit",
                "required_evidence": _complete_commit_evidence(),
            },
            available_evidence=_complete_commit_evidence(),
            recovery_summary={"transaction_id": "tx-approval-terminal", "record_found": True, "status": "finished"},
        )
    )

    gate = runtime.build_governed_replay_approval_gate(
        runtime.build_governed_replay_execution_gateway_preview(decision)
    )

    assert decision["decision_type"] == "blocked_terminal_recovery"
    assert gate["approval_status"] == "blocked"
    assert gate["approval_granted"] is False
    _assert_approval_gate_never_allows_execution(gate)


def test_controlled_dispatch_preview_blocks_when_approval_not_granted(tmp_path):
    runtime = _runtime(tmp_path)
    approval, gateway, _decision = _approval_and_gateway(runtime, "tx-dispatch-preview", _complete_commit_evidence())

    preview = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)

    assert approval["approval_status"] == "review_required"
    assert approval["approval_granted"] is False
    assert preview["source"] == "governed_replay_controlled_dispatch_preview_v1"
    assert preview["dispatch_status"] == "preview_blocked"
    assert preview["blocked_reason"] == "approval_not_granted"
    _assert_dispatch_preview_never_allows_execution(preview)


def test_controlled_dispatch_preview_blocks_blocked_approval_gate(tmp_path):
    runtime = _runtime(tmp_path)
    approval, gateway, _decision = _approval_and_gateway(runtime, "tx-dispatch-blocked", ["transaction_record"])

    preview = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)

    assert approval["approval_status"] == "blocked"
    assert preview["dispatch_status"] == "blocked"
    assert preview["dispatch_eligible"] is False
    assert preview["execution_allowed"] is False
    _assert_dispatch_preview_never_allows_execution(preview)


def test_controlled_dispatch_preview_never_allows_dispatch_in_v1(tmp_path):
    runtime = _runtime(tmp_path)
    approval, gateway, _decision = _approval_and_gateway(runtime, "tx-dispatch-never", _complete_commit_evidence())

    preview = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)

    _assert_dispatch_preview_never_allows_execution(preview)


def test_controlled_dispatch_execution_envelope_is_preview_only(tmp_path):
    runtime = _runtime(tmp_path)
    approval, gateway, _decision = _approval_and_gateway(runtime, "tx-dispatch-envelope", _complete_commit_evidence())

    preview = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)
    envelope = preview["execution_envelope"]

    assert envelope["preview_only"] is True
    assert envelope["requires_human_approval"] is True
    assert envelope["approval_granted"] is False
    assert envelope["transaction_id"] == "tx-dispatch-envelope"
    assert envelope["action"] == "commit"
    assert envelope["risk_level"] == "high"
    _assert_dispatch_preview_never_allows_execution(preview)


def test_controlled_dispatch_evidence_capture_contract_reflects_gateway_evidence(tmp_path):
    runtime = _runtime(tmp_path)
    approval, gateway, _decision = _approval_and_gateway(
        runtime,
        "tx-dispatch-evidence",
        ["transaction_record", "mutation_context"],
    )

    preview = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)
    capture = preview["evidence_capture_contract"]

    assert capture["capture_required"] is True
    assert capture["capture_mode"] == "preview_only"
    assert capture["required_evidence"] == gateway["evidence_contract"]["required_evidence"]
    assert capture["available_evidence"] == gateway["evidence_contract"]["available_evidence"]
    assert capture["missing_evidence"] == gateway["evidence_contract"]["missing_evidence"]
    assert capture["evidence_complete"] is False
    assert capture["decision_type"] == "blocked_missing_evidence"
    assert capture["transaction_id"] == "tx-dispatch-evidence"


def test_controlled_dispatch_debug_context_contains_dispatch_fields(tmp_path):
    runtime = _runtime(tmp_path)
    approval, gateway, _decision = _approval_and_gateway(runtime, "tx-dispatch-debug", _complete_commit_evidence())

    preview = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)
    debug = preview["debug_context"]

    assert debug["source"] == "governed_replay_controlled_dispatch_preview_v1"
    assert debug["replay_id"] == "replay-tx-dispatch-debug"
    assert debug["transaction_id"] == "tx-dispatch-debug"
    assert debug["action"] == "commit"
    assert debug["approval_status"] == "review_required"
    assert debug["approval_granted"] is False
    assert debug["dispatch_status"] == "preview_blocked"
    assert debug["dispatch_eligible"] is False
    assert debug["execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["executor_dispatch_allowed"] is False
    assert debug["scheduler_dispatch_allowed"] is False
    assert debug["command_execution_allowed"] is False
    assert debug["auto_commit"] is False
    assert debug["auto_rollback"] is False
    assert debug["blocked_reason"] == "approval_not_granted"
    assert debug["risk_level"] == "high"


def test_controlled_dispatch_preserves_terminal_block(tmp_path):
    runtime = _runtime(tmp_path)
    decision = runtime.build_replay_execution_decision(
        runtime._build_replay_execution_preflight(
            {
                "transaction_id": "tx-dispatch-terminal",
                "replay_action": "commit",
                "required_evidence": _complete_commit_evidence(),
            },
            available_evidence=_complete_commit_evidence(),
            recovery_summary={"transaction_id": "tx-dispatch-terminal", "record_found": True, "status": "finished"},
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)
    approval = runtime.build_governed_replay_approval_gate(gateway)

    preview = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)

    assert decision["decision_type"] == "blocked_terminal_recovery"
    assert approval["approval_status"] == "blocked"
    assert preview["dispatch_status"] == "blocked"
    assert preview["blocked_reason"] == "terminal recovery state"
    _assert_dispatch_preview_never_allows_execution(preview)


def test_controlled_dispatch_preserves_missing_evidence_block(tmp_path):
    runtime = _runtime(tmp_path)
    approval, gateway, decision = _approval_and_gateway(runtime, "tx-dispatch-missing", ["transaction_record"])

    preview = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)

    assert decision["decision_type"] == "blocked_missing_evidence"
    assert approval["approval_status"] == "blocked"
    assert preview["dispatch_status"] == "blocked"
    assert "missing required evidence" in preview["blocked_reason"]
    _assert_dispatch_preview_never_allows_execution(preview)


def test_dispatch_authorization_requires_review_for_preview_blocked_dispatch(tmp_path):
    runtime = _runtime(tmp_path)
    dispatch, _approval, _gateway, _decision = _dispatch_preview(
        runtime,
        "tx-auth-review",
        _complete_commit_evidence(),
    )

    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)

    assert dispatch["dispatch_status"] == "preview_blocked"
    assert authorization["authorization_status"] == "review_required"
    assert authorization["authorization_required"] is True
    _assert_authorization_never_allows_execution(authorization)


def test_dispatch_authorization_blocks_blocked_dispatch(tmp_path):
    runtime = _runtime(tmp_path)
    dispatch, _approval, _gateway, _decision = _dispatch_preview(
        runtime,
        "tx-auth-blocked",
        ["transaction_record"],
    )

    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)

    assert dispatch["dispatch_status"] == "blocked"
    assert authorization["authorization_status"] == "blocked"
    assert authorization["authorization_granted"] is False
    assert authorization["sandbox_eligible"] is False
    _assert_authorization_never_allows_execution(authorization)


def test_dispatch_authorization_never_grants_authorization_in_v1(tmp_path):
    runtime = _runtime(tmp_path)
    preview_blocked, *_ = _dispatch_preview(runtime, "tx-auth-never-preview", _complete_commit_evidence())
    blocked, *_ = _dispatch_preview(runtime, "tx-auth-never-blocked", ["transaction_record"])

    for dispatch in (preview_blocked, blocked):
        authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)
        assert authorization["authorization_required"] is True
        assert authorization["authorization_granted"] is False
        assert authorization["execution_allowed"] is False


def test_dispatch_authorization_never_allows_execution_or_mutation(tmp_path):
    runtime = _runtime(tmp_path)
    dispatch, *_ = _dispatch_preview(runtime, "tx-auth-flags", _complete_commit_evidence())

    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)

    _assert_authorization_never_allows_execution(authorization)


def test_dispatch_authorization_sandbox_preview_is_never_eligible_in_v1(tmp_path):
    runtime = _runtime(tmp_path)
    dispatch, *_ = _dispatch_preview(runtime, "tx-auth-sandbox", _complete_commit_evidence())

    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)
    sandbox = authorization["sandbox_preview"]

    assert sandbox["preview_only"] is True
    assert sandbox["sandbox_eligible"] is False
    assert sandbox["sandbox_execution_allowed"] is False
    assert sandbox["reason"] == "approval_not_granted"
    _assert_authorization_never_allows_execution(authorization)


def test_dispatch_authorization_execution_ticket_is_preview_only(tmp_path):
    runtime = _runtime(tmp_path)
    dispatch, *_ = _dispatch_preview(runtime, "tx-auth-ticket", _complete_commit_evidence())

    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)
    ticket = authorization["execution_ticket"]

    assert ticket["ticket_type"] == "dispatch_authorization_preview"
    assert ticket["preview_only"] is True
    assert ticket["ticket_status"] == "not_issued"
    assert ticket["authorization_granted"] is False
    assert ticket["execution_allowed"] is False
    assert ticket["dispatch_eligible"] is False
    assert ticket["sandbox_eligible"] is False
    assert ticket["transaction_id"] == "tx-auth-ticket"
    assert ticket["action"] == "commit"


def test_dispatch_authorization_immutable_audit_record_preview_contains_authorization_fields(tmp_path):
    runtime = _runtime(tmp_path)
    dispatch, *_ = _dispatch_preview(runtime, "tx-auth-audit", _complete_commit_evidence())

    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)
    audit = authorization["immutable_audit_record"]

    assert audit["record_type"] == "dispatch_authorization_preview"
    assert audit["immutable"] is True
    assert audit["preview_only"] is True
    assert audit["source"] == "governed_replay_dispatch_authorization_v1"
    assert audit["transaction_id"] == "tx-auth-audit"
    assert audit["action"] == "commit"
    assert audit["authorization_status"] == "review_required"
    assert audit["authorization_granted"] is False
    assert audit["dispatch_status"] == "preview_blocked"
    assert audit["dispatch_eligible"] is False
    assert audit["sandbox_eligible"] is False
    assert audit["execution_allowed"] is False
    assert audit["mutation_allowed"] is False


def test_dispatch_authorization_debug_context_contains_authorization_fields(tmp_path):
    runtime = _runtime(tmp_path)
    dispatch, *_ = _dispatch_preview(runtime, "tx-auth-debug", _complete_commit_evidence())

    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)
    debug = authorization["debug_context"]

    assert debug["source"] == "governed_replay_dispatch_authorization_v1"
    assert debug["replay_id"] == "replay-tx-auth-debug"
    assert debug["transaction_id"] == "tx-auth-debug"
    assert debug["action"] == "commit"
    assert debug["dispatch_status"] == "preview_blocked"
    assert debug["dispatch_eligible"] is False
    assert debug["authorization_status"] == "review_required"
    assert debug["authorization_required"] is True
    assert debug["authorization_granted"] is False
    assert debug["sandbox_eligible"] is False
    assert debug["execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["executor_dispatch_allowed"] is False
    assert debug["scheduler_dispatch_allowed"] is False
    assert debug["command_execution_allowed"] is False
    assert debug["auto_commit"] is False
    assert debug["auto_rollback"] is False
    assert debug["blocked_reason"] == "approval_not_granted"
    assert debug["risk_level"] == "high"


def test_dispatch_authorization_preserves_missing_evidence_block(tmp_path):
    runtime = _runtime(tmp_path)
    dispatch, _approval, _gateway, decision = _dispatch_preview(
        runtime,
        "tx-auth-missing",
        ["transaction_record"],
    )

    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)

    assert decision["decision_type"] == "blocked_missing_evidence"
    assert dispatch["dispatch_status"] == "blocked"
    assert authorization["authorization_status"] == "blocked"
    assert "missing required evidence" in authorization["blocked_reason"]
    _assert_authorization_never_allows_execution(authorization)


def test_dispatch_authorization_preserves_terminal_block(tmp_path):
    runtime = _runtime(tmp_path)
    decision = runtime.build_replay_execution_decision(
        runtime._build_replay_execution_preflight(
            {
                "transaction_id": "tx-auth-terminal",
                "replay_action": "commit",
                "required_evidence": _complete_commit_evidence(),
            },
            available_evidence=_complete_commit_evidence(),
            recovery_summary={"transaction_id": "tx-auth-terminal", "record_found": True, "status": "finished"},
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)
    approval = runtime.build_governed_replay_approval_gate(gateway)
    dispatch = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)

    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)

    assert decision["decision_type"] == "blocked_terminal_recovery"
    assert dispatch["dispatch_status"] == "blocked"
    assert authorization["authorization_status"] == "blocked"
    assert authorization["blocked_reason"] == "terminal recovery state"
    _assert_authorization_never_allows_execution(authorization)


def test_immutable_journal_preview_is_preview_only(tmp_path):
    runtime = _runtime(tmp_path)
    authorization, dispatch, approval, gateway, decision = _authorization_preview(
        runtime,
        "tx-journal-preview",
        _complete_commit_evidence(),
    )

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )

    assert preview["source"] == "governed_replay_immutable_journal_preview_v1"
    assert preview["journal_status"] == "preview_only"
    assert preview["journal_entry_preview"]["preview_only"] is True
    assert preview["journal_entry_preview"]["immutable"] is True
    _assert_immutable_journal_never_allows_execution_or_write(preview)


def test_immutable_journal_preview_never_allows_write_append_or_persist(tmp_path):
    runtime = _runtime(tmp_path)
    authorization, dispatch, approval, gateway, decision = _authorization_preview(
        runtime,
        "tx-journal-write",
        _complete_commit_evidence(),
    )

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )
    entry = preview["journal_entry_preview"]

    assert entry["write_allowed"] is False
    assert entry["append_allowed"] is False
    assert entry["persist_allowed"] is False
    _assert_immutable_journal_never_allows_execution_or_write(preview)


def test_immutable_journal_preview_preserves_blocked_authorization(tmp_path):
    runtime = _runtime(tmp_path)
    authorization, dispatch, approval, gateway, decision = _authorization_preview(
        runtime,
        "tx-journal-blocked",
        ["transaction_record"],
    )

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )
    entry = preview["journal_entry_preview"]

    assert authorization["authorization_status"] == "blocked"
    assert preview["authorization_status"] == "blocked"
    assert entry["authorization_blocked"] is True
    assert entry["authorization_pending"] is False
    assert "missing required evidence" in preview["blocked_reason"]


def test_immutable_journal_preview_represents_review_required_authorization(tmp_path):
    runtime = _runtime(tmp_path)
    authorization, dispatch, approval, gateway, decision = _authorization_preview(
        runtime,
        "tx-journal-review",
        _complete_commit_evidence(),
    )

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )
    entry = preview["journal_entry_preview"]

    assert authorization["authorization_status"] == "review_required"
    assert preview["authorization_status"] == "review_required"
    assert entry["authorization_blocked"] is False
    assert entry["authorization_pending"] is True
    assert preview["blocked_reason"] == "approval_not_granted"


def test_immutable_journal_lineage_contains_all_governance_stages(tmp_path):
    runtime = _runtime(tmp_path)
    authorization, dispatch, approval, gateway, decision = _authorization_preview(
        runtime,
        "tx-journal-lineage",
        _complete_commit_evidence(),
    )

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )

    assert [item["stage"] for item in preview["replay_lineage"]] == [
        "replay_request",
        "preflight",
        "decision",
        "gateway_preview",
        "approval_gate",
        "controlled_dispatch_preview",
        "dispatch_authorization",
        "immutable_journal_preview",
    ]
    for item in preview["replay_lineage"]:
        assert "stage" in item
        assert "status" in item
        assert "source" in item
        assert "blocked_reason" in item


def test_immutable_journal_causality_chain_reflects_terminal_block(tmp_path):
    runtime = _runtime(tmp_path)
    decision = runtime.build_replay_execution_decision(
        runtime._build_replay_execution_preflight(
            {
                "transaction_id": "tx-journal-terminal",
                "replay_action": "commit",
                "required_evidence": _complete_commit_evidence(),
            },
            available_evidence=_complete_commit_evidence(),
            recovery_summary={"transaction_id": "tx-journal-terminal", "record_found": True, "status": "finished"},
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)
    approval = runtime.build_governed_replay_approval_gate(gateway)
    dispatch = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)
    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )
    chain = preview["causality_chain"]

    assert chain["decision_type"] == "blocked_terminal_recovery"
    assert chain["terminal_blocked"] is True
    assert chain["missing_evidence_blocked"] is False
    assert chain["execution_allowed"] is False


def test_immutable_journal_causality_chain_reflects_missing_evidence_block(tmp_path):
    runtime = _runtime(tmp_path)
    authorization, dispatch, approval, gateway, decision = _authorization_preview(
        runtime,
        "tx-journal-missing",
        ["transaction_record"],
    )

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )
    chain = preview["causality_chain"]

    assert chain["decision_type"] == "blocked_missing_evidence"
    assert chain["missing_evidence_blocked"] is True
    assert chain["terminal_blocked"] is False
    assert chain["execution_allowed"] is False


def test_immutable_journal_runtime_provenance_contains_sources_and_depth(tmp_path):
    runtime = _runtime(tmp_path)
    authorization, dispatch, approval, gateway, decision = _authorization_preview(
        runtime,
        "tx-journal-provenance",
        _complete_commit_evidence(),
    )

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )
    provenance = preview["runtime_provenance"]

    assert provenance["provenance_type"] == "governed_replay_runtime_preview"
    assert provenance["transaction_id"] == "tx-journal-provenance"
    assert "governed_replay_dispatch_authorization_v1" in provenance["sources"]
    assert "governed_replay_immutable_journal_preview_v1" in provenance["sources"]
    assert provenance["governance_depth"] == 8
    assert provenance["final_status"] == "preview_only"
    assert provenance["immutable_preview"] is True
    assert provenance["write_allowed"] is False


def test_immutable_journal_debug_context_contains_journal_fields(tmp_path):
    runtime = _runtime(tmp_path)
    authorization, dispatch, approval, gateway, decision = _authorization_preview(
        runtime,
        "tx-journal-debug",
        _complete_commit_evidence(),
    )

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )
    debug = preview["debug_context"]

    assert debug["source"] == "governed_replay_immutable_journal_preview_v1"
    assert debug["replay_id"] == "replay-tx-journal-debug"
    assert debug["transaction_id"] == "tx-journal-debug"
    assert debug["action"] == "commit"
    assert debug["authorization_status"] == "review_required"
    assert debug["authorization_granted"] is False
    assert debug["journal_status"] == "preview_only"
    assert debug["execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["executor_dispatch_allowed"] is False
    assert debug["scheduler_dispatch_allowed"] is False
    assert debug["command_execution_allowed"] is False
    assert debug["auto_commit"] is False
    assert debug["auto_rollback"] is False
    assert debug["blocked_reason"] == "approval_not_granted"
    assert debug["risk_level"] == "high"


def test_immutable_journal_never_allows_execution_or_mutation(tmp_path):
    runtime = _runtime(tmp_path)
    authorization, dispatch, approval, gateway, decision = _authorization_preview(
        runtime,
        "tx-journal-never",
        _complete_commit_evidence(),
    )

    preview = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )

    _assert_immutable_journal_never_allows_execution_or_write(preview)


def test_governance_state_snapshot_is_preview_only(tmp_path):
    runtime = _runtime(tmp_path)
    journal, *_ = _immutable_journal_preview(runtime, "tx-snapshot-preview", _complete_commit_evidence())

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)

    assert snapshot["source"] == "governed_replay_governance_state_snapshot_v1"
    assert snapshot["snapshot_status"] == "preview_only"
    assert snapshot["snapshot_preview"]["preview_only"] is True
    assert snapshot["snapshot_preview"]["immutable"] is True
    _assert_snapshot_never_allows_execution_or_write(snapshot)


def test_governance_state_snapshot_never_allows_write_persist_or_append(tmp_path):
    runtime = _runtime(tmp_path)
    journal, *_ = _immutable_journal_preview(runtime, "tx-snapshot-write", _complete_commit_evidence())

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)
    preview = snapshot["snapshot_preview"]

    assert preview["write_allowed"] is False
    assert preview["persist_allowed"] is False
    assert preview["append_allowed"] is False
    _assert_snapshot_never_allows_execution_or_write(snapshot)


def test_governance_state_snapshot_freeze_frame_contains_final_status(tmp_path):
    runtime = _runtime(tmp_path)
    journal, *_ = _immutable_journal_preview(runtime, "tx-snapshot-freeze", _complete_commit_evidence())

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)
    freeze = snapshot["freeze_frame"]

    assert freeze["freeze_type"] == "governance_state_freeze_frame"
    assert freeze["immutable"] is True
    assert freeze["preview_only"] is True
    assert freeze["final_status"] == "preview_only"
    assert freeze["governance_depth"] == 9
    assert freeze["execution_allowed"] is False
    assert freeze["mutation_allowed"] is False


def test_governance_state_snapshot_reconstruction_payload_contains_full_stage_order(tmp_path):
    runtime = _runtime(tmp_path)
    journal, *_ = _immutable_journal_preview(runtime, "tx-snapshot-reconstruct", _complete_commit_evidence())

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)
    payload = snapshot["deterministic_reconstruction_payload"]

    assert payload["reconstruction_type"] == "deterministic_governance_reconstruction_preview"
    assert payload["stage_order"] == [
        "replay_request",
        "preflight",
        "decision",
        "gateway_preview",
        "approval_gate",
        "controlled_dispatch_preview",
        "dispatch_authorization",
        "immutable_journal_preview",
        "governance_state_snapshot",
    ]
    assert payload["stage_statuses"]["governance_state_snapshot"] == "preview_only"
    assert payload["governance_depth"] == 9


def test_governance_state_snapshot_replayable_state_contains_governance_flags(tmp_path):
    runtime = _runtime(tmp_path)
    journal, *_ = _immutable_journal_preview(runtime, "tx-snapshot-replayable", _complete_commit_evidence())

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)
    state = snapshot["replayable_governance_state"]

    assert state["replayable"] is True
    assert state["preview_only"] is True
    assert state["current_stage"] == "governance_state_snapshot"
    assert state["final_status"] == "preview_only"
    assert state["governance_flags"] == snapshot["governance_flags"]
    assert state["governance_flags"]["execution_allowed"] is False
    assert state["governance_flags"]["write_allowed"] is False


def test_governance_state_snapshot_lineage_digest_counts_stages(tmp_path):
    runtime = _runtime(tmp_path)
    journal, *_ = _immutable_journal_preview(runtime, "tx-snapshot-digest", _complete_commit_evidence())

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)
    digest = snapshot["lineage_digest"]

    assert digest["lineage_stage_count"] == 9
    assert digest["governance_depth"] == 9
    assert digest["first_stage"] == "replay_request"
    assert digest["last_stage"] == "governance_state_snapshot"
    assert digest["sources_count"] == 9
    assert digest["final_status"] == "preview_only"


def test_governance_state_snapshot_preserves_terminal_block(tmp_path):
    runtime = _runtime(tmp_path)
    decision = runtime.build_replay_execution_decision(
        runtime._build_replay_execution_preflight(
            {
                "transaction_id": "tx-snapshot-terminal",
                "replay_action": "commit",
                "required_evidence": _complete_commit_evidence(),
            },
            available_evidence=_complete_commit_evidence(),
            recovery_summary={"transaction_id": "tx-snapshot-terminal", "record_found": True, "status": "finished"},
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)
    approval = runtime.build_governed_replay_approval_gate(gateway)
    dispatch = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)
    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)
    journal = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)

    assert snapshot["freeze_frame"]["terminal_blocked"] is True
    assert snapshot["deterministic_reconstruction_payload"]["blocked_reason"] == "terminal recovery state"
    assert snapshot["blocked_reason"] == "terminal recovery state"


def test_governance_state_snapshot_preserves_missing_evidence_block(tmp_path):
    runtime = _runtime(tmp_path)
    journal, *_ = _immutable_journal_preview(runtime, "tx-snapshot-missing", ["transaction_record"])

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)

    assert snapshot["freeze_frame"]["missing_evidence_blocked"] is True
    assert "missing required evidence" in snapshot["blocked_reason"]
    assert snapshot["deterministic_reconstruction_payload"]["blocked_reason"] == snapshot["blocked_reason"]


def test_governance_state_snapshot_debug_context_contains_snapshot_fields(tmp_path):
    runtime = _runtime(tmp_path)
    journal, *_ = _immutable_journal_preview(runtime, "tx-snapshot-debug", _complete_commit_evidence())

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)
    debug = snapshot["debug_context"]

    assert debug["source"] == "governed_replay_governance_state_snapshot_v1"
    assert debug["replay_id"] == "replay-tx-snapshot-debug"
    assert debug["transaction_id"] == "tx-snapshot-debug"
    assert debug["action"] == "commit"
    assert debug["snapshot_status"] == "preview_only"
    assert debug["final_status"] == "preview_only"
    assert debug["governance_depth"] == 9
    assert debug["blocked_reason"] == "approval_not_granted"
    assert debug["risk_level"] == "high"
    assert debug["execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["executor_dispatch_allowed"] is False
    assert debug["scheduler_dispatch_allowed"] is False
    assert debug["command_execution_allowed"] is False
    assert debug["authorization_granted"] is False
    assert debug["auto_commit"] is False
    assert debug["auto_rollback"] is False
    assert debug["write_allowed"] is False
    assert debug["persist_allowed"] is False
    assert debug["append_allowed"] is False


def test_governance_state_snapshot_never_allows_execution_or_mutation(tmp_path):
    runtime = _runtime(tmp_path)
    journal, *_ = _immutable_journal_preview(runtime, "tx-snapshot-never", _complete_commit_evidence())

    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)

    _assert_snapshot_never_allows_execution_or_write(snapshot)


def test_governance_diff_verification_single_snapshot_has_no_diff(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot = _governance_snapshot(runtime, "tx-diff-single", _complete_commit_evidence())

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot)

    assert result["verification_status"] == "preview_only"
    assert result["governance_diff"]["has_diff"] is False
    assert result["governance_diff"]["changed_fields"] == []
    assert result["deterministic_verification"]["deterministic"] is True
    assert result["reconstruction_consistency_check"]["reconstruction_consistent"] is True
    _assert_diff_verification_never_allows_execution(result)


def test_governance_diff_verification_detects_changed_blocked_reason(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-diff-reason", _complete_commit_evidence())
    snapshot_b = {**snapshot_a, "blocked_reason": "changed reason"}

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    assert result["governance_diff"]["has_diff"] is True
    assert "blocked_reason" in result["governance_diff"]["changed_fields"]
    assert result["governance_diff"]["blocked_reason_changed"] is True
    assert result["deterministic_verification"]["blocked_reason_consistent"] is False


def test_governance_diff_verification_detects_risk_level_change(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-diff-risk", _complete_commit_evidence())
    snapshot_b = {**snapshot_a, "risk_level": "medium"}

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    assert "risk_level" in result["governance_diff"]["changed_fields"]
    assert result["governance_diff"]["risk_level_changed"] is True
    assert result["debug_context"]["risk_level"] == "medium"


def test_governance_diff_verification_detects_capability_flag_escalation(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-diff-escalation", _complete_commit_evidence())
    snapshot_b = {**snapshot_a, "execution_allowed": True}

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    drift = result["capability_drift_detection"]
    assert drift["drift_detected"] is True
    assert drift["unsafe_flag_escalation_detected"] is True
    assert "execution_allowed" in drift["drifted_flags"]
    _assert_diff_verification_never_allows_execution(result)


def test_governance_diff_verification_preserves_safe_flags(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot = _governance_snapshot(runtime, "tx-diff-safe", _complete_commit_evidence())

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot)
    drift = result["capability_drift_detection"]

    assert drift["drift_detected"] is False
    assert drift["drifted_flags"] == []
    assert drift["safe_flags_preserved"] is True
    assert drift["unsafe_flag_escalation_detected"] is False


def test_governance_diff_verification_detects_stage_order_drift(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-diff-stage", _complete_commit_evidence())
    payload = dict(snapshot_a["deterministic_reconstruction_payload"])
    payload["stage_order"] = list(reversed(payload["stage_order"]))
    snapshot_b = {**snapshot_a, "deterministic_reconstruction_payload": payload}

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    assert result["deterministic_verification"]["deterministic"] is False
    assert result["deterministic_verification"]["stage_order_consistent"] is False
    assert result["reconstruction_consistency_check"]["reconstruction_consistent"] is False


def test_governance_diff_verification_checks_reconstruction_consistency(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-diff-reconstruction", _complete_commit_evidence())
    digest = dict(snapshot_a["lineage_digest"])
    digest["governance_depth"] = 99
    snapshot_b = {**snapshot_a, "lineage_digest": digest}

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)
    check = result["reconstruction_consistency_check"]

    assert check["reconstruction_consistent"] is False
    assert check["governance_depth_consistent"] is False
    assert check["sources_consistent"] is True
    assert check["lineage_stage_count_consistent"] is True


def test_governance_diff_verification_debug_context_contains_diff_fields(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-diff-debug", _complete_commit_evidence())
    snapshot_b = {**snapshot_a, "blocked_reason": "debug change"}

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)
    debug = result["debug_context"]

    assert debug["source"] == "governed_replay_governance_state_diff_verification_v1"
    assert debug["replay_id"] == "replay-tx-diff-debug"
    assert debug["transaction_id"] == "tx-diff-debug"
    assert debug["action"] == "commit"
    assert debug["verification_status"] == "preview_only"
    assert debug["has_diff"] is True
    assert debug["drift_detected"] is False
    assert debug["unsafe_flag_escalation_detected"] is False
    assert debug["deterministic"] is False
    assert debug["reconstruction_consistent"] is True
    assert debug["blocked_reason"] == "debug change"
    assert debug["risk_level"] == "high"
    assert debug["execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["executor_dispatch_allowed"] is False
    assert debug["scheduler_dispatch_allowed"] is False
    assert debug["command_execution_allowed"] is False
    assert debug["authorization_granted"] is False
    assert debug["auto_commit"] is False
    assert debug["auto_rollback"] is False


def test_governance_diff_verification_never_allows_execution_or_mutation(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot = _governance_snapshot(runtime, "tx-diff-never", _complete_commit_evidence())

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot)

    _assert_diff_verification_never_allows_execution(result)


def test_governance_diff_verification_preserves_terminal_block(tmp_path):
    runtime = _runtime(tmp_path)
    decision = runtime.build_replay_execution_decision(
        runtime._build_replay_execution_preflight(
            {
                "transaction_id": "tx-diff-terminal",
                "replay_action": "commit",
                "required_evidence": _complete_commit_evidence(),
            },
            available_evidence=_complete_commit_evidence(),
            recovery_summary={"transaction_id": "tx-diff-terminal", "record_found": True, "status": "finished"},
        )
    )
    gateway = runtime.build_governed_replay_execution_gateway_preview(decision)
    approval = runtime.build_governed_replay_approval_gate(gateway)
    dispatch = runtime.build_governed_replay_controlled_dispatch_preview(approval, gateway_preview=gateway)
    authorization = runtime.build_governed_replay_dispatch_authorization(dispatch)
    journal = runtime.build_governed_replay_immutable_journal_preview(
        authorization,
        dispatch_preview=dispatch,
        approval_gate=approval,
        gateway_preview=gateway,
        decision=decision,
    )
    snapshot = runtime.build_governed_replay_governance_state_snapshot(journal)

    result = runtime.build_governed_replay_governance_state_diff_verification(snapshot)

    assert result["snapshot_a"]["freeze_frame"]["terminal_blocked"] is True
    assert result["blocked_reason"] == "terminal recovery state"
    assert result["deterministic_verification"]["deterministic"] is True
    _assert_diff_verification_never_allows_execution(result)


def test_policy_resolution_marks_stable_preview_when_no_drift(tmp_path):
    runtime = _runtime(tmp_path)
    verification = _stable_diff_verification(runtime, "tx-policy-stable")

    result = runtime.build_governed_replay_policy_resolution(verification)

    assert result["policy_resolution_status"] == "preview_only"
    assert result["risk_classification"]["risk_category"] == "stable_preview"
    assert result["governance_outcome"]["governance_stable"] is True
    assert result["governance_outcome"]["blocked"] is False
    _assert_policy_resolution_never_allows_execution(result)


def test_policy_resolution_detects_capability_escalation_risk(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-policy-capability", _complete_commit_evidence())
    snapshot_b = {**snapshot_a, "execution_allowed": True}
    verification = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    result = runtime.build_governed_replay_policy_resolution(verification)

    assert result["risk_classification"]["risk_category"] == "capability_escalation"
    assert result["risk_classification"]["unsafe_flag_escalation_detected"] is True
    assert result["capability_integrity_status"]["stable"] is False
    assert result["policy_decision"]["recommended_action"] == "investigate_capability_drift"


def test_policy_resolution_detects_deterministic_drift(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-policy-deterministic", _complete_commit_evidence())
    payload = dict(snapshot_a["deterministic_reconstruction_payload"])
    payload["stage_order"] = list(reversed(payload["stage_order"]))
    snapshot_b = {**snapshot_a, "deterministic_reconstruction_payload": payload}
    verification = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    result = runtime.build_governed_replay_policy_resolution(verification)

    assert result["risk_classification"]["risk_category"] == "deterministic_drift"
    assert result["risk_classification"]["deterministic_failure_detected"] is True
    assert result["deterministic_integrity_status"]["stable"] is False
    assert result["policy_decision"]["recommended_action"] == "review_deterministic_pipeline"


def test_policy_resolution_detects_reconstruction_inconsistency(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-policy-reconstruction", _complete_commit_evidence())
    digest = dict(snapshot_a["lineage_digest"])
    digest["governance_depth"] = 99
    snapshot_b = {**snapshot_a, "lineage_digest": digest}
    verification = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    result = runtime.build_governed_replay_policy_resolution(verification)

    assert result["risk_classification"]["risk_category"] == "reconstruction_inconsistency"
    assert result["risk_classification"]["reconstruction_inconsistency_detected"] is True
    assert result["reconstruction_integrity_status"]["stable"] is False
    assert result["policy_decision"]["recommended_action"] == "review_reconstruction_consistency"


def test_policy_resolution_routes_capability_escalation_review(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-policy-route-capability", _complete_commit_evidence())
    snapshot_b = {**snapshot_a, "mutation_allowed": True}
    verification = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    result = runtime.build_governed_replay_policy_resolution(verification)

    assert result["escalation_routing"]["escalation_required"] is True
    assert result["escalation_routing"]["escalation_target"] == "capability_integrity_review"


def test_policy_resolution_routes_deterministic_review(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-policy-route-deterministic", _complete_commit_evidence())
    snapshot_b = {**snapshot_a, "blocked_reason": "changed deterministic reason"}
    verification = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    result = runtime.build_governed_replay_policy_resolution(verification)

    assert result["escalation_routing"]["escalation_required"] is True
    assert result["escalation_routing"]["escalation_target"] == "deterministic_verification_review"


def test_policy_resolution_routes_reconstruction_review(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-policy-route-reconstruction", _complete_commit_evidence())
    payload = dict(snapshot_a["deterministic_reconstruction_payload"])
    payload["sources"] = list(payload["sources"]) + ["extra_source"]
    snapshot_b = {**snapshot_a, "deterministic_reconstruction_payload": payload}
    verification = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    result = runtime.build_governed_replay_policy_resolution(verification)

    assert result["escalation_routing"]["escalation_required"] is True
    assert result["escalation_routing"]["escalation_target"] == "reconstruction_integrity_review"


def test_policy_resolution_blocks_unstable_governance(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot_a = _governance_snapshot(runtime, "tx-policy-block", _complete_commit_evidence())
    snapshot_b = {**snapshot_a, "authorization_granted": True}
    verification = runtime.build_governed_replay_governance_state_diff_verification(snapshot_a, snapshot_b)

    result = runtime.build_governed_replay_policy_resolution(verification)

    assert result["governance_outcome"]["blocked"] is True
    assert result["governance_outcome"]["governance_stable"] is False
    assert result["policy_decision"]["escalation_required"] is True


def test_policy_resolution_recommends_maintain_preview_state_when_stable(tmp_path):
    runtime = _runtime(tmp_path)
    verification = _stable_diff_verification(runtime, "tx-policy-maintain")

    result = runtime.build_governed_replay_policy_resolution(verification)

    assert result["policy_decision"]["recommended_action"] == "maintain_preview_state"
    assert result["policy_decision"]["governance_stable"] is True
    assert result["escalation_routing"]["escalation_target"] == "stable_preview_review"


def test_policy_resolution_debug_context_contains_resolution_fields(tmp_path):
    runtime = _runtime(tmp_path)
    verification = _stable_diff_verification(runtime, "tx-policy-debug")

    result = runtime.build_governed_replay_policy_resolution(verification)
    debug = result["debug_context"]

    assert debug["source"] == "governed_replay_policy_resolution_v1"
    assert debug["replay_id"] == "replay-tx-policy-debug"
    assert debug["transaction_id"] == "tx-policy-debug"
    assert debug["action"] == "commit"
    assert debug["policy_resolution_status"] == "preview_only"
    assert debug["risk_category"] == "stable_preview"
    assert debug["escalation_required"] is False
    assert debug["escalation_target"] == "stable_preview_review"
    assert debug["governance_stable"] is True
    assert debug["deterministic"] is True
    assert debug["reconstruction_consistent"] is True
    assert debug["capability_integrity_preserved"] is True
    assert debug["blocked_reason"] == "approval_not_granted"
    assert debug["risk_level"] == "high"
    assert debug["execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["executor_dispatch_allowed"] is False
    assert debug["scheduler_dispatch_allowed"] is False
    assert debug["command_execution_allowed"] is False
    assert debug["authorization_granted"] is False
    assert debug["auto_commit"] is False
    assert debug["auto_rollback"] is False


def test_policy_resolution_never_allows_execution_or_mutation(tmp_path):
    runtime = _runtime(tmp_path)
    verification = _stable_diff_verification(runtime, "tx-policy-never")

    result = runtime.build_governed_replay_policy_resolution(verification)

    _assert_policy_resolution_never_allows_execution(result)


def _policy_resolution(runtime: TaskRuntime, transaction_id: str):
    diff = _stable_diff_verification(runtime, transaction_id)
    return runtime.build_governed_replay_policy_resolution(diff), diff


def _assert_core_seal_never_allows_execution(seal: dict) -> None:
    assert seal["execution_allowed"] is False
    assert seal["mutation_allowed"] is False
    assert seal["executor_dispatch_allowed"] is False
    assert seal["scheduler_dispatch_allowed"] is False
    assert seal["command_execution_allowed"] is False
    assert seal["authorization_granted"] is False
    assert seal["auto_commit"] is False
    assert seal["auto_rollback"] is False


def test_aer_governance_core_seal_builds_complete_stage_order(tmp_path):
    runtime = _runtime(tmp_path)
    resolution, diff = _policy_resolution(runtime, "tx-seal-order")

    seal = runtime.build_governed_replay_aer_governance_core_seal(
        resolution,
        diff_verification=diff,
    )

    assert seal["seal_status"] == "preview_only"
    assert seal["stage_order"][-1] == "aer_governance_core_seal"
    assert len(seal["stage_order"]) == 12
    _assert_core_seal_never_allows_execution(seal)


def test_aer_governance_core_seal_detects_unstable_governance(tmp_path):
    runtime = _runtime(tmp_path)
    snapshot = _governance_snapshot(runtime, "tx-seal-unstable", _complete_commit_evidence())
    mutated = dict(snapshot)
    flags = dict(mutated["governance_flags"])
    flags["execution_allowed"] = True
    mutated["governance_flags"] = flags

    diff = runtime.build_governed_replay_governance_state_diff_verification(
        snapshot,
        snapshot_b=mutated,
    )
    resolution = runtime.build_governed_replay_policy_resolution(diff)

    seal = runtime.build_governed_replay_aer_governance_core_seal(
        resolution,
        diff_verification=diff,
    )

    assert seal["governance_stable"] is False
    assert seal["integrity_checks"]["capability_integrity_preserved"] is False
    _assert_core_seal_never_allows_execution(seal)


def test_aer_governance_core_seal_debug_context_contains_flags(tmp_path):
    runtime = _runtime(tmp_path)
    resolution, diff = _policy_resolution(runtime, "tx-seal-debug")

    seal = runtime.build_governed_replay_aer_governance_core_seal(
        resolution,
        diff_verification=diff,
    )

    debug = seal["debug_context"]

    assert debug["source"] == "governed_replay_aer_governance_core_seal_v1"
    assert debug["execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["authorization_granted"] is False
