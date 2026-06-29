from __future__ import annotations

import hashlib
import pathlib
import subprocess

from core.runtime.task_runtime import TaskRuntime
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.external, pytest.mark.slow]




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


def _sandbox_execution_ticket_preview(runtime: TaskRuntime, transaction_id: str):
    resolution, diff = _policy_resolution(runtime, transaction_id)
    seal = runtime.build_governed_replay_aer_governance_core_seal(
        resolution,
        diff_verification=diff,
    )
    return runtime.build_governed_sandboxed_execution_ticket_preview(
        seal,
        policy_resolution=resolution,
        diff_verification=diff,
    )


def _assert_sandbox_execution_ticket_never_allows_execution(preview: dict) -> None:
    assert preview["execution_allowed"] is False
    assert preview["mutation_allowed"] is False
    assert preview["executor_dispatch_allowed"] is False
    assert preview["scheduler_dispatch_allowed"] is False
    assert preview["command_execution_allowed"] is False
    assert preview["authorization_granted"] is False
    assert preview["auto_commit"] is False
    assert preview["auto_rollback"] is False
    assert preview["shell_execution_allowed"] is False
    assert preview["filesystem_write_allowed"] is False
    assert preview["network_access_allowed"] is False
    assert preview["subprocess_allowed"] is False
    assert preview["repo_mutation_allowed"] is False


def test_execution_ticket_preview_is_preview_only(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-ticket-preview")

    assert preview["source"] == "governed_sandboxed_execution_ticket_preview_v1"
    assert preview["execution_ticket_status"] == "preview_only"
    assert preview["execution_ticket"]["ticket_type"] == "sandboxed_execution_ticket_preview"
    assert preview["execution_ticket"]["preview_only"] is True
    assert preview["execution_ticket"]["immutable"] is True
    assert preview["execution_ticket"]["governance_sealed"] is True
    _assert_sandbox_execution_ticket_never_allows_execution(preview)


def test_execution_ticket_never_allows_execution(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-ticket-never")
    ticket = preview["execution_ticket"]

    assert ticket["execution_allowed"] is False
    assert ticket["mutation_allowed"] is False
    assert ticket["dispatch_allowed"] is False
    assert ticket["shell_execution_allowed"] is False
    _assert_sandbox_execution_ticket_never_allows_execution(preview)


def test_capability_envelope_is_readonly_only(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-envelope-readonly")
    envelope = preview["capability_envelope"]

    assert envelope["envelope_type"] == "sandboxed_capability_envelope_preview"
    assert envelope["preview_only"] is True
    assert envelope["readonly_execution_only"] is True
    assert envelope["mutation_execution_allowed"] is False
    assert envelope["shell_execution_allowed"] is False
    assert envelope["filesystem_write_allowed"] is False
    assert envelope["network_access_allowed"] is False
    assert envelope["subprocess_allowed"] is False
    assert envelope["repo_mutation_allowed"] is False


def test_capability_envelope_blocks_mutation_execution(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-envelope-blocks")
    envelope = preview["capability_envelope"]

    assert envelope["mutation_execution_allowed"] is False
    assert preview["mutation_allowed"] is False
    assert preview["filesystem_write_allowed"] is False
    assert preview["repo_mutation_allowed"] is False
    assert preview["subprocess_allowed"] is False


def test_allowed_readonly_commands_are_whitelisted(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-allowed-commands")

    assert preview["allowed_readonly_commands"] == [
        "pwd",
        "dir",
        "ls",
        "git status",
        "python -m compileall",
        "pytest --collect-only",
    ]


def test_blocked_commands_contains_mutation_commands(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-blocked-commands")
    blocked_commands = preview["blocked_commands"]

    for command in (
        "rm",
        "del",
        "move",
        "rename",
        "git commit",
        "git push",
        "git reset",
        "pip install",
        "powershell",
        "bash",
        "cmd /c",
        "python script_that_writes.py",
    ):
        assert command in blocked_commands


def test_sandbox_dispatch_preview_never_allows_dispatch(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-sandbox-dispatch")
    dispatch = preview["sandbox_dispatch_preview"]

    assert dispatch["dispatch_type"] == "sandboxed_dispatch_preview"
    assert dispatch["preview_only"] is True
    assert dispatch["readonly_dispatch_only"] is True
    assert dispatch["dispatch_allowed"] is False
    assert dispatch["execution_allowed"] is False
    assert dispatch["mutation_allowed"] is False
    assert dispatch["shell_execution_allowed"] is False


def test_execution_verification_contract_requires_governance_seal(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-verification-contract")
    contract = preview["execution_verification_contract"]

    assert contract["verification_type"] == "sandbox_execution_verification_preview"
    assert contract["preview_only"] is True
    assert contract["deterministic_verification_required"] is True
    assert contract["evidence_capture_required"] is True
    assert contract["rollback_required_before_mutation"] is True
    assert contract["governance_seal_required"] is True


def test_evidence_capture_contract_never_persists_logs(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-evidence-contract")
    contract = preview["evidence_capture_contract"]

    assert contract["evidence_type"] == "sandbox_execution_evidence_preview"
    assert contract["preview_only"] is True
    assert contract["capture_stdout"] is True
    assert contract["capture_stderr"] is True
    assert contract["capture_exit_code"] is True
    assert contract["capture_command"] is True
    assert contract["capture_runtime_metadata"] is True
    assert contract["persist_execution_logs"] is False


def test_execution_ticket_debug_context_contains_sandbox_fields(tmp_path):
    runtime = _runtime(tmp_path)

    preview = _sandbox_execution_ticket_preview(runtime, "tx-ticket-debug")
    debug = preview["debug_context"]

    assert debug["source"] == "governed_sandboxed_execution_ticket_preview_v1"
    assert debug["replay_id"] == "replay-tx-ticket-debug"
    assert debug["transaction_id"] == "tx-ticket-debug"
    assert debug["action"] == "commit"
    assert debug["execution_ticket_status"] == "preview_only"
    assert debug["readonly_execution_only"] is True
    assert debug["shell_execution_allowed"] is False
    assert debug["filesystem_write_allowed"] is False
    assert debug["network_access_allowed"] is False
    assert debug["subprocess_allowed"] is False
    assert debug["repo_mutation_allowed"] is False
    assert debug["execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["authorization_granted"] is False
    assert debug["blocked_reason"] == "approval_not_granted"
    assert debug["risk_level"] == "high"
    _assert_sandbox_execution_ticket_never_allows_execution(preview)


def _readonly_command_gate(
    runtime: TaskRuntime,
    command: str,
    *,
    enable_readonly_execution: bool = False,
    readonly_execution_mode: str = "preview",
):
    command_slug = "".join(char if char.isalnum() else "-" for char in command.lower()).strip("-")
    return runtime.build_readonly_command_execution_gate(
        _sandbox_execution_ticket_preview(runtime, f"tx-command-{command_slug}"),
        command=command,
        enable_readonly_execution=enable_readonly_execution,
        readonly_execution_mode=readonly_execution_mode,
    )


def _assert_readonly_command_gate_never_executes(gate: dict) -> None:
    assert gate["execution_allowed"] is False
    assert gate["mutation_allowed"] is False
    assert gate["executor_dispatch_allowed"] is False
    assert gate["scheduler_dispatch_allowed"] is False
    assert gate["command_execution_allowed"] is False
    assert gate["authorization_granted"] is False
    assert gate["auto_commit"] is False
    assert gate["auto_rollback"] is False


def test_readonly_command_gate_allows_pwd_preview(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "pwd")

    assert gate["source"] == "readonly_command_execution_gate_v1"
    assert gate["normalized_command"] == "pwd"
    assert gate["command_category"] == "readonly_allowed"
    assert gate["command_allowed"] is True
    assert gate["deny_reason"] == ""
    assert gate["readonly_match"] is True
    assert gate["blocked_match"] is False
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_allows_git_status_preview(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "git status")

    assert gate["normalized_command"] == "git status"
    assert gate["command_category"] == "readonly_allowed"
    assert gate["command_allowed"] is True
    assert gate["execution_plan_preview"]["command_allowed"] is True
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_allows_compileall_preview(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "python -m compileall")

    assert gate["normalized_command"] == "python -m compileall"
    assert gate["command_category"] == "readonly_allowed"
    assert gate["command_allowed"] is True
    assert gate["readonly_match"] is True
    assert gate["blocked_match"] is False
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_blocks_rm(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "rm -rf workspace")

    assert gate["command_category"] == "blocked_mutation"
    assert gate["command_allowed"] is False
    assert gate["deny_reason"] == "blocked command pattern"
    assert gate["blocked_match"] is True
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_blocks_git_commit(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "git commit -m test")

    assert gate["command_category"] == "blocked_mutation"
    assert gate["command_allowed"] is False
    assert gate["deny_reason"] == "blocked command pattern"
    assert gate["blocked_match"] is True
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_blocks_pip_install(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "pip install requests")

    assert gate["command_category"] == "blocked_network_or_install"
    assert gate["command_allowed"] is False
    assert gate["deny_reason"] == "blocked command pattern"
    assert gate["blocked_match"] is True
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_blocks_shell_escape(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "bash -lc ls")

    assert gate["command_category"] == "blocked_shell"
    assert gate["command_allowed"] is False
    assert gate["deny_reason"] == "blocked command pattern"
    assert gate["blocked_match"] is True
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_blocks_unknown_command(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "git log")

    assert gate["command_category"] == "unknown"
    assert gate["command_allowed"] is False
    assert gate["deny_reason"] == "command not in readonly whitelist"
    assert gate["readonly_match"] is False
    assert gate["blocked_match"] is False
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_allowed_preview_still_never_executes(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "ls")
    plan = gate["execution_plan_preview"]

    assert gate["command_allowed"] is True
    assert plan["preview_only"] is True
    assert plan["dispatch_allowed"] is False
    assert plan["execution_allowed"] is False
    assert plan["readonly_execution_only"] is True
    assert plan["mutation_allowed"] is False
    assert plan["expected_evidence"] == ["stdout", "stderr", "exit_code", "command", "runtime_metadata"]
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_evidence_capture_plan_is_preview_only(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "dir")
    evidence = gate["evidence_capture_plan"]
    verification = gate["verification_plan"]

    assert evidence["preview_only"] is True
    assert evidence["capture_stdout"] is True
    assert evidence["capture_stderr"] is True
    assert evidence["capture_exit_code"] is True
    assert evidence["capture_command"] is True
    assert evidence["capture_runtime_metadata"] is True
    assert evidence["persist_logs"] is False
    assert evidence["write_allowed"] is False
    assert verification["preview_only"] is True
    assert verification["verify_exit_code"] is True
    assert verification["verify_no_mutation"] is True
    assert verification["verify_command_in_whitelist"] is True
    assert verification["verify_blacklist_not_matched"] is True
    assert verification["deterministic_verification_required"] is True
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_command_gate_debug_context_contains_command_fields(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "  Git   Status  ")
    debug = gate["debug_context"]

    assert debug["source"] == "readonly_command_execution_gate_v1"
    assert debug["command"] == "  Git   Status  "
    assert debug["normalized_command"] == "git status"
    assert debug["command_category"] == "readonly_allowed"
    assert debug["command_allowed"] is True
    assert debug["deny_reason"] == ""
    assert debug["readonly_match"] is True
    assert debug["blocked_match"] is False
    assert debug["execution_allowed"] is False
    assert debug["command_execution_allowed"] is False
    assert debug["mutation_allowed"] is False
    assert debug["auto_commit"] is False
    assert debug["auto_rollback"] is False
    _assert_readonly_command_gate_never_executes(gate)


def test_readonly_execution_unlock_preview_mode_keeps_git_status_non_executable(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(runtime, "git status")

    assert gate["command_allowed"] is True
    assert gate["execution_allowed"] is False
    assert gate["command_execution_allowed"] is False
    assert gate["readonly_execution_mode"] == "preview"
    assert gate["enable_readonly_execution"] is False


def test_readonly_execution_unlock_execute_mode_allows_git_status_contract(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert gate["command_allowed"] is True
    assert gate["execution_allowed"] is True
    assert gate["command_execution_allowed"] is True
    assert gate["execution_plan_preview"]["execution_allowed"] is True
    assert gate["execution_plan_preview"]["command_execution_allowed"] is True
    assert gate["mutation_allowed"] is False
    assert gate["executor_dispatch_allowed"] is False
    assert gate["scheduler_dispatch_allowed"] is False
    assert gate["authorization_granted"] is False
    assert gate["auto_commit"] is False
    assert gate["auto_rollback"] is False


def test_readonly_execution_unlock_execute_mode_still_blocks_git_commit(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(
        runtime,
        "git commit -m test",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert gate["command_allowed"] is False
    assert gate["execution_allowed"] is False
    assert gate["command_execution_allowed"] is False
    assert gate["deny_reason"] == "blocked command pattern"
    assert gate["blocked_pattern_classification"] == "mutation"


def test_readonly_execution_unlock_execute_mode_keeps_unknown_blocked(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(
        runtime,
        "python scripts/custom.py",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert gate["command_allowed"] is False
    assert gate["execution_allowed"] is False
    assert gate["command_execution_allowed"] is False
    assert gate["deny_reason"] == "command not in readonly whitelist"
    assert gate["command_category"] == "unknown"


def test_readonly_execution_unlock_normalizes_git_status(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(
        runtime,
        "   GIT   STATUS   ",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert gate["normalized_command"] == "git status"
    assert gate["command_allowed"] is True
    assert gate["execution_allowed"] is True
    assert gate["command_execution_allowed"] is True


def test_readonly_execution_unlock_allowed_command_has_contract_plans(tmp_path):
    runtime = _runtime(tmp_path)

    gate = _readonly_command_gate(
        runtime,
        "pytest --collect-only tests",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert gate["command_allowed"] is True
    assert gate["execution_allowed"] is True
    assert gate["command_execution_allowed"] is True
    assert gate["execution_plan_preview"]["preview_only"] is True
    assert gate["evidence_capture_plan"]["preview_only"] is True
    assert gate["evidence_capture_plan"]["persist_logs"] is False
    assert gate["evidence_capture_plan"]["write_allowed"] is False
    assert gate["verification_plan"]["preview_only"] is True
    assert gate["verification_plan"]["verify_no_mutation"] is True


def test_readonly_execution_unlock_safety_regression_blocks_dangerous_commands(tmp_path):
    runtime = _runtime(tmp_path)

    for command in (
        'python -c "print(1)"',
        "pip install requests",
        "curl https://example.com",
        "rm -rf .",
        "git push",
        "echo hi > file.txt",
    ):
        gate = _readonly_command_gate(
            runtime,
            command,
            enable_readonly_execution=True,
            readonly_execution_mode="execute_readonly",
        )

        assert gate["command_allowed"] is False
        assert gate["execution_allowed"] is False
        assert gate["command_execution_allowed"] is False
        assert gate["deny_reason"] == "blocked command pattern"
        assert gate["blocked_match"] is True
        assert gate["mutation_allowed"] is False
        assert gate["executor_dispatch_allowed"] is False
        assert gate["scheduler_dispatch_allowed"] is False
        assert gate["authorization_granted"] is False
        assert gate["auto_commit"] is False
        assert gate["auto_rollback"] is False


def _run_readonly_command(
    runtime: TaskRuntime,
    command: str,
    *,
    enable_readonly_execution: bool = False,
    readonly_execution_mode: str = "preview",
    timeout_seconds: int = 10,
):
    return runtime.run_readonly_command_execution_gate(
        _sandbox_execution_ticket_preview(runtime, "tx-controlled-readonly"),
        command=command,
        cwd="E:\\zero_ai",
        timeout_seconds=timeout_seconds,
        enable_readonly_execution=enable_readonly_execution,
        readonly_execution_mode=readonly_execution_mode,
    )


def _assert_controlled_result_contract(result: dict) -> None:
    for field in (
        "status",
        "command",
        "normalized_command",
        "command_allowed",
        "execution_allowed",
        "command_execution_allowed",
        "deny_reason",
        "blocked_pattern_classification",
        "execution_plan_preview",
        "evidence_capture_plan",
        "verification_plan",
        "stdout",
        "stderr",
        "returncode",
        "duration_seconds",
        "timeout_seconds",
        "executed",
        "execution_record",
        "replay_record",
        "evidence_record",
        "verification_record",
    ):
        assert field in result


def test_controlled_readonly_execution_preview_mode_does_not_execute(tmp_path):
    runtime = _runtime(tmp_path)

    result = _run_readonly_command(runtime, "git status")

    _assert_controlled_result_contract(result)
    assert result["command_allowed"] is True
    assert result["execution_allowed"] is False
    assert result["command_execution_allowed"] is False
    assert result["executed"] is False
    assert result["status"] in {"blocked", "preview"}
    assert result["stdout"] == ""
    assert result["stderr"] == ""


def test_controlled_readonly_execution_execute_mode_runs_git_status(tmp_path):
    runtime = _runtime(tmp_path)

    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    _assert_controlled_result_contract(result)
    assert result["command_execution_allowed"] is True
    assert result["executed"] is True
    assert result["status"] in {"executed", "failed"}
    assert "stdout" in result
    assert "stderr" in result
    assert "returncode" in result


def test_controlled_readonly_execution_blocked_command_does_not_execute(tmp_path):
    runtime = _runtime(tmp_path)

    result = _run_readonly_command(
        runtime,
        "git push",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert result["executed"] is False
    assert result["command_execution_allowed"] is False
    assert result["deny_reason"] == "blocked command pattern"
    assert result["status"] == "blocked"


def test_controlled_readonly_execution_unknown_command_does_not_execute(tmp_path):
    runtime = _runtime(tmp_path)

    result = _run_readonly_command(
        runtime,
        "python scripts/custom.py",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert result["executed"] is False
    assert result["command_execution_allowed"] is False
    assert result["deny_reason"] == "command not in readonly whitelist"
    assert result["status"] == "blocked"


def test_controlled_readonly_execution_unsafe_paths_do_not_execute(tmp_path):
    runtime = _runtime(tmp_path)

    for command in (
        "python -m compileall ..\\outside",
        "pytest --collect-only ..\\tests",
        "python -m compileall core\\runtime\\task_runtime.py && git status",
    ):
        result = _run_readonly_command(
            runtime,
            command,
            enable_readonly_execution=True,
            readonly_execution_mode="execute_readonly",
        )

        assert result["executed"] is False
        assert result["command_execution_allowed"] is False or result["deny_reason"] == "unsafe readonly command path"
        assert result["deny_reason"] in {"unsafe readonly command path", "blocked command pattern"}


def test_controlled_readonly_execution_safe_compileall_executes(tmp_path):
    runtime = _runtime(tmp_path)

    result = _run_readonly_command(
        runtime,
        "python -m compileall core\\runtime\\task_runtime.py",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    _assert_controlled_result_contract(result)
    assert result["executed"] is True
    assert result["command_execution_allowed"] is True
    assert "returncode" in result
    assert result["status"] in {"executed", "failed"}


def test_controlled_readonly_execution_timeout_contract(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", fake_run)

    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
        timeout_seconds=1,
    )

    assert result["status"] == "timeout"
    assert result["executed"] is True
    assert result["returncode"] is None
    assert "timeout" in result["stderr"] or "timeout" in result["deny_reason"]


def test_controlled_readonly_execution_subprocess_uses_shell_false(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    calls = []

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        return Completed()

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", fake_run)

    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert result["executed"] is True
    assert result["status"] == "executed"
    assert calls
    assert calls[0].get("shell") is False


def test_readonly_execution_evidence_executed_command_has_all_records(tmp_path):
    runtime = _runtime(tmp_path)

    result = _run_readonly_command(
        runtime,
        "python -m compileall core\\runtime\\task_runtime.py",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    _assert_controlled_result_contract(result)
    assert result["executed"] is True
    assert result["execution_record"]["record_type"] == "readonly_command_execution"
    assert result["replay_record"]["replay_type"] == "readonly_command_replay"
    assert result["replay_record"]["replayable"] is True
    assert result["evidence_record"]["evidence_type"] == "command_execution_evidence"
    assert result["verification_record"]["verification_type"] == "readonly_execution_verification"


def test_readonly_execution_evidence_digest_is_deterministic(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "fixed stdout"
        stderr = "fixed stderr"
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())

    first = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    second = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert first["execution_record"]["stdout_digest"] == second["execution_record"]["stdout_digest"]
    assert first["execution_record"]["stderr_digest"] == second["execution_record"]["stderr_digest"]


def test_readonly_execution_evidence_preview_mode_has_records_not_replayable(tmp_path):
    runtime = _runtime(tmp_path)

    result = _run_readonly_command(runtime, "git status")

    _assert_controlled_result_contract(result)
    assert result["executed"] is False
    assert result["status"] in {"preview", "blocked"}
    assert result["execution_record"]["executed"] is False
    assert result["replay_record"]["replayable"] is False
    assert result["verification_record"]["verification_status"] in {"preview", "blocked"}


def test_readonly_execution_evidence_blocked_command_has_blocked_records(tmp_path):
    runtime = _runtime(tmp_path)

    result = _run_readonly_command(
        runtime,
        "git push",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert result["executed"] is False
    assert result["replay_record"]["replayable"] is False
    assert result["verification_record"]["verification_status"] == "blocked"
    assert result["deny_reason"] == "blocked command pattern"
    assert result["execution_record"]["executed"] is False
    assert result["evidence_record"]["executed"] is False


def test_readonly_execution_evidence_unsafe_path_has_blocked_records(tmp_path):
    runtime = _runtime(tmp_path)

    result = _run_readonly_command(
        runtime,
        "python -m compileall ..\\outside",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert result["executed"] is False
    assert result["replay_record"]["replayable"] is False
    assert result["verification_record"]["verification_status"] == "blocked"
    assert result["deny_reason"] == "unsafe readonly command path"
    assert result["execution_record"]["executed"] is False
    assert result["evidence_record"]["executed"] is False


def test_readonly_execution_evidence_output_preview_is_bounded(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    long_stdout = "x" * 5000

    class Completed:
        stdout = long_stdout
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())

    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )

    assert len(result["execution_record"]["stdout_preview"]) <= 2000
    assert result["execution_record"]["stdout_digest"] == hashlib.sha256(long_stdout.encode("utf-8")).hexdigest()


def test_readonly_execution_evidence_replay_uses_whitelist_argv(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())

    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    replay_argv = result["replay_record"]["replay_argv"]

    assert isinstance(replay_argv, list)
    assert replay_argv == ["git", "status", "--short"]
    assert "shell=True" not in replay_argv
    assert result["verification_record"]["checks"]["argv_generated_from_whitelist"] is True


def test_readonly_execution_evidence_timeout_has_timeout_verification(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", fake_run)

    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
        timeout_seconds=1,
    )

    assert result["status"] == "timeout"
    assert result["executed"] is True
    assert result["verification_record"]["verification_status"] == "timeout"
    assert isinstance(result["replay_record"]["replayable"], bool)


def test_runtime_evidence_registry_can_register_executed_result(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "python -m compileall core\\runtime\\task_runtime.py",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()

    record = registry.register_execution_result(result)

    assert len(registry.list_records()) == 1
    assert record["record_type"] == "runtime_evidence_registry_record"
    assert record["execution_record"]
    assert record["replay_record"]
    assert record["evidence_record"]
    assert record["verification_record"]


def test_runtime_evidence_registry_can_query_by_evidence_id(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)

    found = registry.get_by_evidence_id(record["evidence_id"])

    assert found is not None
    assert found["registry_record_id"] == record["registry_record_id"]


def test_runtime_evidence_registry_query_by_status_and_executed(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    registry.register_execution_result(result)

    executed_records = registry.query(executed=True)
    status_records = registry.query(status=result["status"])

    assert executed_records
    assert status_records
    assert result["status"] in {"executed", "failed"}


def test_runtime_evidence_registry_stores_blocked_result(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "git push",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)

    assert record["executed"] is False
    assert record["replay_record"]["replayable"] is False
    assert registry.query(executed=False)


def test_runtime_evidence_registry_reconstructs_replay_request(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)

    request = registry.build_replay_request(record["evidence_id"])

    assert request["replay_request_type"] == "readonly_command_replay_request"
    assert isinstance(request["replay_argv"], list)
    assert request["replay_safety"] == "readonly_only"


def test_runtime_evidence_registry_reconstructs_blocked_replay_request(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "git push",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)

    request = registry.build_replay_request(record["evidence_id"])

    assert request["replay_request_type"] == "readonly_command_replay_request"
    assert request["replayable"] is False
    assert request["deny_reason"]


def test_runtime_evidence_registry_builds_verification_lineage(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)

    lineage = registry.build_verification_lineage(record["evidence_id"])

    assert lineage["lineage_type"] == "readonly_execution_verification_lineage"
    assert lineage["verification_status"]
    assert isinstance(lineage["checks"], dict)
    assert "stdout_digest" in lineage
    assert "stderr_digest" in lineage


def test_runtime_evidence_registry_query_handles_missing_fields(tmp_path):
    registry = TaskRuntime.build_runtime_evidence_registry()
    minimal = {
        "command": "manual",
        "normalized_command": "manual",
        "status": "blocked",
        "executed": False,
        "returncode": None,
    }

    record = registry.register_execution_result(minimal)
    results = registry.query(status="blocked", replayable=False, verification_status="")

    assert record["evidence_id"]
    assert results


def test_runtime_evidence_registry_does_not_write_files(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(runtime, "git status")
    writes = []

    def blocked_open(*args, **kwargs):
        writes.append(("open", args, kwargs))
        raise AssertionError("registry should not write files")

    def blocked_write_text(*args, **kwargs):
        writes.append(("write_text", args, kwargs))
        raise AssertionError("registry should not write files")

    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr(pathlib.Path, "write_text", blocked_write_text)

    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    assert registry.list_records()
    assert registry.get_record(record["registry_record_id"])
    assert registry.query(command_contains="git")
    assert not writes


def test_runtime_replay_engine_deterministic_digest_passes(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())

    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    report = registry.replay(record["evidence_id"])

    assert report["replay_report_type"] == "readonly_command_replay_validation"
    assert report["replay_executed"] is True
    assert report["replay_validation_status"] == "passed"
    assert report["returncode_match"] is True
    assert report["stdout_digest_match"] is True
    assert report["stderr_digest_match"] is True


def test_runtime_replay_engine_detects_digest_mismatch(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class FirstCompleted:
        stdout = "ok"
        stderr = ""
        returncode = 0

    class ReplayCompleted:
        stdout = "changed"
        stderr = ""
        returncode = 0

    responses = [FirstCompleted(), ReplayCompleted()]
    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))

    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    report = registry.replay(record["evidence_id"])

    assert report["replay_validation_status"] == "mismatch"
    assert report["stdout_digest_match"] is False


def test_runtime_replay_engine_blocked_record_does_not_execute(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "git push",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)

    report = registry.replay(record["evidence_id"])

    assert report["replay_executed"] is False
    assert report["replay_validation_status"] == "blocked"
    assert report["deny_reason"]


def test_runtime_replay_engine_invalid_replay_argv_blocked(tmp_path):
    registry = TaskRuntime.build_runtime_evidence_registry()
    result = {
        "command": "git status",
        "normalized_command": "git status",
        "status": "executed",
        "executed": True,
        "returncode": 0,
        "execution_record": {
            "stdout_digest": hashlib.sha256(b"").hexdigest(),
            "stderr_digest": hashlib.sha256(b"").hexdigest(),
        },
        "evidence_record": {"evidence_id": "invalid-argv-evidence"},
        "replay_record": {
            "replayable": True,
            "replay_command": "git status",
            "replay_normalized_command": "git status",
            "replay_argv": "git status",
            "replay_cwd": "E:\\zero_ai",
            "expected_returncode": 0,
            "expected_stdout_digest": hashlib.sha256(b"").hexdigest(),
            "expected_stderr_digest": hashlib.sha256(b"").hexdigest(),
            "replay_safety": "readonly_only",
        },
        "verification_record": {"verification_status": "passed", "checks": {}},
    }
    record = registry.register_execution_result(result)

    report = registry.replay(record["evidence_id"])

    assert report["replay_executed"] is False
    assert report["replay_validation_status"] == "blocked"
    assert report["deny_reason"] == "invalid replay argv"


def test_runtime_replay_engine_timeout_contract(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", timeout_run)
    report = registry.replay(record["evidence_id"], timeout_seconds=1)

    assert report["replay_validation_status"] == "timeout"
    assert report["replay_executed"] is True
    assert report["status"] == "timeout"


def test_runtime_replay_engine_report_contains_bounded_previews(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class FirstCompleted:
        stdout = "ok"
        stderr = ""
        returncode = 0

    class ReplayCompleted:
        stdout = "x" * 5000
        stderr = ""
        returncode = 0

    responses = [FirstCompleted(), ReplayCompleted()]
    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    report = registry.replay(record["evidence_id"])

    assert len(report["stdout_preview"]) <= 2000


def test_runtime_replay_engine_reports_are_memory_only(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    writes = []

    def blocked_open(*args, **kwargs):
        writes.append(("open", args, kwargs))
        raise AssertionError("replay should not write files")

    def blocked_write_text(*args, **kwargs):
        writes.append(("write_text", args, kwargs))
        raise AssertionError("replay should not write files")

    def blocked_json_dump(*args, **kwargs):
        writes.append(("json.dump", args, kwargs))
        raise AssertionError("replay should not write files")

    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr(pathlib.Path, "write_text", blocked_write_text)
    monkeypatch.setattr("core.runtime.task_runtime.json.dump", blocked_json_dump)

    report = registry.replay(record["evidence_id"])

    assert report["replay_executed"] is True
    assert registry.list_replay_reports()
    assert registry.get_replay_reports(record["evidence_id"])
    assert not writes


def test_runtime_replay_engine_subprocess_uses_shell_false(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    calls = []

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        return Completed()

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", fake_run)
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])

    assert len(calls) >= 2
    assert all(call.get("shell") is False for call in calls)


def test_runtime_execution_chain_register_creates_execution_node(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    nodes = registry.list_execution_chain_nodes()

    assert len(nodes) >= 1
    assert nodes[0]["node_type"] == "readonly_execution"
    assert nodes[0]["evidence_id"] == record["evidence_id"]


def test_runtime_execution_chain_replay_creates_validation_node_and_edge(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])

    nodes = registry.list_execution_chain_nodes()
    edges = registry.list_execution_chain_edges()

    assert any(node["node_type"] == "readonly_replay_validation" for node in nodes)
    assert any(edge["edge_type"] == "replay_validation_of" for edge in edges)


def test_runtime_execution_chain_for_evidence(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])

    chain = registry.get_execution_chain_for_evidence(record["evidence_id"])

    assert chain["chain_type"] == "readonly_execution_chain"
    assert chain["execution_node"]
    assert len(chain["replay_nodes"]) >= 1
    assert len(chain["edges"]) >= 1


def test_runtime_execution_ancestry_detects_passed_replay(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])

    ancestry = registry.build_execution_ancestry(record["evidence_id"])

    assert ancestry["latest_validation_status"] == "passed"
    assert ancestry["validation_count"] >= 1
    assert ancestry["has_mismatch"] is False


def test_runtime_execution_ancestry_detects_mismatch(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class FirstCompleted:
        stdout = "ok"
        stderr = ""
        returncode = 0

    class ReplayCompleted:
        stdout = "changed"
        stderr = ""
        returncode = 0

    responses = [FirstCompleted(), ReplayCompleted()]
    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])

    ancestry = registry.build_execution_ancestry(record["evidence_id"])

    assert ancestry["has_mismatch"] is True
    assert ancestry["latest_validation_status"] == "mismatch"


def test_runtime_replay_lineage_counts_statuses(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class OkCompleted:
        stdout = "ok"
        stderr = ""
        returncode = 0

    class ChangedCompleted:
        stdout = "changed"
        stderr = ""
        returncode = 0

    responses = [OkCompleted(), OkCompleted(), ChangedCompleted()]
    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])
    registry.replay(record["evidence_id"])

    lineage = registry.build_replay_lineage(record["evidence_id"])

    assert lineage["passed_count"] >= 1
    assert lineage["mismatch_count"] >= 1
    assert lineage["latest_report"]


def test_runtime_execution_chain_unknown_evidence_safe_return(tmp_path):
    registry = TaskRuntime.build_runtime_evidence_registry()

    chain = registry.get_execution_chain_for_evidence("missing")
    ancestry = registry.build_execution_ancestry("missing")
    lineage = registry.build_replay_lineage("missing")

    assert chain["found"] is False
    assert ancestry["found"] is False
    assert lineage["found"] is False
    assert chain["reason"]
    assert ancestry["reason"]
    assert lineage["reason"]


def test_runtime_execution_chain_blocked_replay_appears_in_lineage(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "git push",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])

    lineage = registry.build_replay_lineage(record["evidence_id"])
    ancestry = registry.build_execution_ancestry(record["evidence_id"])

    assert lineage["blocked_count"] >= 1
    assert ancestry["has_blocked_replay"] is True


def test_runtime_execution_chain_does_not_write_files(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    writes = []

    def blocked_open(*args, **kwargs):
        writes.append(("open", args, kwargs))
        raise AssertionError("chain graph should not write files")

    def blocked_write_text(*args, **kwargs):
        writes.append(("write_text", args, kwargs))
        raise AssertionError("chain graph should not write files")

    def blocked_json_dump(*args, **kwargs):
        writes.append(("json.dump", args, kwargs))
        raise AssertionError("chain graph should not write files")

    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr(pathlib.Path, "write_text", blocked_write_text)
    monkeypatch.setattr("core.runtime.task_runtime.json.dump", blocked_json_dump)

    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])
    registry.get_execution_chain_for_evidence(record["evidence_id"])
    registry.build_execution_ancestry(record["evidence_id"])
    registry.build_replay_lineage(record["evidence_id"])

    assert not writes


def test_runtime_governance_evaluation_healthy_replay_allows_future_governed_mutation(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])
    registry.replay(record["evidence_id"])

    health = registry.evaluate_execution_health(record["evidence_id"])
    stability = registry.evaluate_replay_stability(record["evidence_id"])
    confidence = registry.evaluate_verification_confidence(record["evidence_id"])
    readiness = registry.evaluate_mutation_readiness(record["evidence_id"])

    assert health["health_status"] == "healthy"
    assert stability["replay_stability_status"] == "stable"
    assert confidence["confidence_level"] == "high"
    assert readiness["mutation_ready"] is True
    assert readiness["governance_decision"] == "allow_future_governed_mutation"


def test_runtime_governance_evaluation_mismatch_degrades_runtime(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class FirstCompleted:
        stdout = "ok"
        stderr = ""
        returncode = 0

    class ReplayCompleted:
        stdout = "changed"
        stderr = ""
        returncode = 0

    responses = [FirstCompleted(), ReplayCompleted()]
    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])

    health = registry.evaluate_execution_health(record["evidence_id"])
    stability = registry.evaluate_replay_stability(record["evidence_id"])
    confidence = registry.evaluate_verification_confidence(record["evidence_id"])
    readiness = registry.evaluate_mutation_readiness(record["evidence_id"])

    assert health["health_status"] in {"degraded", "unstable"}
    assert stability["replay_deterministic"] is False
    assert confidence["confidence_level"] in {"low", "untrusted"}
    assert readiness["mutation_ready"] is False
    assert readiness["governance_decision"] == "deny_mutation"


def test_runtime_governance_evaluation_timeout_affects_stability(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", timeout_run)
    registry.replay(record["evidence_id"])

    stability = registry.evaluate_replay_stability(record["evidence_id"])
    readiness = registry.evaluate_mutation_readiness(record["evidence_id"])

    assert stability["timeout_count"] >= 1
    assert stability["replay_stability_status"] != "stable"
    assert readiness["mutation_ready"] is False


def test_runtime_governance_evaluation_blocked_replay_is_unsafe(tmp_path):
    runtime = _runtime(tmp_path)
    result = _run_readonly_command(
        runtime,
        "git push",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])

    health = registry.evaluate_execution_health(record["evidence_id"])
    readiness = registry.evaluate_mutation_readiness(record["evidence_id"])

    assert health["health_status"] in {"blocked", "unstable"}
    assert readiness["governance_decision"] in {"deny_mutation", "unsafe_runtime_state"}


def test_runtime_governance_evaluation_no_replay_is_unknown(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)

    health = registry.evaluate_execution_health(record["evidence_id"])
    stability = registry.evaluate_replay_stability(record["evidence_id"])
    readiness = registry.evaluate_mutation_readiness(record["evidence_id"])

    assert health["health_status"] == "unknown"
    assert stability["replay_stability_status"] == "unknown"
    assert readiness["governance_decision"] == "require_more_replay_validation"


def test_runtime_governance_registry_summary_mixed_results(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class OkCompleted:
        stdout = "ok"
        stderr = ""
        returncode = 0

    class ChangedCompleted:
        stdout = "changed"
        stderr = ""
        returncode = 0

    registry = TaskRuntime.build_runtime_evidence_registry()
    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: OkCompleted())
    healthy = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    healthy_record = registry.register_execution_result(healthy)
    registry.replay(healthy_record["evidence_id"])
    registry.replay(healthy_record["evidence_id"])

    responses = [OkCompleted(), ChangedCompleted()]
    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: responses.pop(0))
    mismatch = _run_readonly_command(
        runtime,
        "python -m compileall core\\runtime\\task_runtime.py",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    mismatch_record = registry.register_execution_result(mismatch)
    registry.replay(mismatch_record["evidence_id"])

    blocked = _run_readonly_command(
        runtime,
        "git push",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry.register_execution_result(blocked)

    summary = registry.evaluate_registry_governance_summary()

    assert summary["total_execution_records"] == 3
    assert "registry_health_score" in summary
    assert "registry_governance_status" in summary
    assert "mutation_ready_count" in summary
    assert "mutation_blocked_count" in summary


def test_runtime_governance_evaluation_unknown_evidence_safe_return(tmp_path):
    registry = TaskRuntime.build_runtime_evidence_registry()

    health = registry.evaluate_execution_health("missing")
    readiness = registry.evaluate_mutation_readiness("missing")

    assert health["found"] is False
    assert readiness["found"] is False
    assert health["reason"]
    assert readiness["reason"]


def test_runtime_governance_evaluation_does_not_write_files(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    class Completed:
        stdout = "ok"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("core.runtime.task_runtime.subprocess.run", lambda *args, **kwargs: Completed())
    result = _run_readonly_command(
        runtime,
        "git status",
        enable_readonly_execution=True,
        readonly_execution_mode="execute_readonly",
    )
    registry = TaskRuntime.build_runtime_evidence_registry()
    record = registry.register_execution_result(result)
    registry.replay(record["evidence_id"])
    writes = []

    def blocked_open(*args, **kwargs):
        writes.append(("open", args, kwargs))
        raise AssertionError("governance evaluation should not write files")

    def blocked_write_text(*args, **kwargs):
        writes.append(("write_text", args, kwargs))
        raise AssertionError("governance evaluation should not write files")

    def blocked_json_dump(*args, **kwargs):
        writes.append(("json.dump", args, kwargs))
        raise AssertionError("governance evaluation should not write files")

    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr(pathlib.Path, "write_text", blocked_write_text)
    monkeypatch.setattr("core.runtime.task_runtime.json.dump", blocked_json_dump)

    registry.evaluate_execution_health(record["evidence_id"])
    registry.evaluate_replay_stability(record["evidence_id"])
    registry.evaluate_verification_confidence(record["evidence_id"])
    registry.evaluate_mutation_readiness(record["evidence_id"])
    registry.evaluate_registry_governance_summary()

    assert not writes
