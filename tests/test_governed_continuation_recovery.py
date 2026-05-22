from __future__ import annotations


def _recovery_metadata() -> dict:
    return {
        "constitutional_activation": True,
        "constitutional_activation_mode": "advisory",
        "constitutional_activation_reason": "missing_recovery_evidence",
        "constitutional_blocked": False,
        "constitutional_enforcement_snapshot": {
            "schema": "runtime_enforcement_decision.v1",
            "classification": "review_required",
            "safe_to_enforce": False,
            "reason": "missing_recovery_evidence",
        },
        "constitutional_continuity_status": "review_required",
        "constitutional_continuity": {
            "kind": "runtime_recovery_constitution",
            "recovery_id": "recovery-continuation",
            "recovery_lineage": ["tx-parent"],
            "recovery_source_state": {"source_transaction_id": "tx-parent"},
            "recovery_target_state": {"status": "recovered"},
        },
        "recovery_constitution_status": "review_required",
    }


def _terminal_metadata() -> dict:
    return {
        "constitutional_activation": True,
        "constitutional_activation_mode": "selective_activation",
        "constitutional_activation_reason": "replay_lineage_corruption",
        "constitutional_blocked": True,
        "constitutional_enforcement_snapshot": {
            "schema": "runtime_enforcement_decision.v1",
            "classification": "block_recommended",
            "safe_to_enforce": True,
            "reason": "replay_lineage_corruption",
        },
        "constitutional_continuity_status": "block_recommended",
    }


def test_scheduler_preserves_replay_lineage_across_continuation() -> None:
    import core.tasks.scheduler as scheduler_module

    metadata = {
        **_recovery_metadata(),
        "constitutional_continuity": {
            "kind": "runtime_replay_constitution",
            "replay_id": "replay-preserved",
            "parent_replay_lineage": ["root-replay"],
            "source_runtime_state_refs": [{"source_session_id": "session-root"}],
        },
        "replay_constitution_status": "review_required",
    }
    summary = scheduler_module._zero_v7333_governed_continuation_summary(
        {"runtime_execution_result": {"metadata": metadata}}
    )

    assert summary["governed_replay_candidate"] is True
    assert summary["replay_continuity_summary"]["parent_replay_lineage"] == ["root-replay"]
    assert summary["continuation_legality"] == "recoverable"


def test_scheduler_preserves_recovery_lineage_across_continuation() -> None:
    import core.tasks.scheduler as scheduler_module

    summary = scheduler_module._zero_v7333_governed_continuation_summary(
        {"runtime_execution_result": {"metadata": _recovery_metadata()}}
    )

    assert summary["governed_recovery_candidate"] is True
    assert summary["recovery_continuity_summary"]["recovery_lineage"] == ["tx-parent"]
    assert summary["continuation_state"] == "governed_continuation_boundary"


def test_scheduler_does_not_blind_retry_terminal_constitutional_blocks(tmp_path) -> None:
    from core.tasks.scheduler import Scheduler

    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))
    task = {
        "task_id": "terminal-no-retry",
        "status": "failed",
        "runtime_execution_result": {"metadata": _terminal_metadata()},
    }

    repairable, reason = scheduler._is_repairable_failure(task)

    assert repairable is False
    assert "terminal constitutional boundary" in reason


def test_graceful_continuation_envelope_is_serializable() -> None:
    import json
    import core.tasks.scheduler as scheduler_module

    summary = scheduler_module._zero_v7333_governed_continuation_summary(
        {"runtime_execution_result": {"metadata": _recovery_metadata()}}
    )
    restored = json.loads(json.dumps(summary, sort_keys=True, default=str))

    assert restored["governed_continuation"] is True
    assert restored["continuation_cycle_id"].startswith("governed-continuation-")
    assert restored["continuation_terminality"] == "non_terminal"


def test_replay_and_recovery_constitution_helpers_remain_compatible() -> None:
    from core.runtime.runtime_recovery_reconstruction import recovery_constitution_summary
    from core.runtime.runtime_replay_engine import replay_constitution_summary

    replay = replay_constitution_summary(
        replay_id="replay-helper",
        source_runtime_state_refs=[{"source_session_id": "session"}],
        transition={"from_status": "replaying", "to_status": "replayed", "allowed": True},
        transition_evidence={"transition_evidence_id": "ev"},
    )
    recovery = recovery_constitution_summary(
        recovery_id="recovery-helper",
        recovery_lineage=["tx"],
        recovery_source_state={"source_transaction_id": "tx", "source_evidence_count": 1},
        recovery_target_state={"status": "recovered"},
        transition={"from_status": "recovering", "to_status": "recovered", "allowed": True},
        transition_evidence={"transition_evidence_id": "ev"},
    )

    assert replay["constitutional_classification"] == "canonical"
    assert recovery["constitutional_classification"] == "canonical"
