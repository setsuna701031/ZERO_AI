from __future__ import annotations


def _classify(from_status: str, to_status: str, **kwargs):
    from core.runtime.runtime_enforcement_readiness import (
        classify_runtime_transition_enforcement,
    )

    return classify_runtime_transition_enforcement(from_status, to_status, **kwargs)


def test_hard_block_candidates_are_safe_to_enforce() -> None:
    cases = [
        ("sealed", "running"),
        ("verified", "running"),
        ("failed", "verifying"),
        ("blocked", "executed"),
        ("rolled_back", "committed"),
        ("replayed", "queued"),
    ]

    for source, target in cases:
        result = _classify(source, target, transition_evidence={"id": "ev"}, source="test")
        assert result["block_recommended"] is True
        assert result["safe_to_enforce"] is True
        assert result["review_required"] is False


def test_sealed_to_sealed_is_not_block_recommended() -> None:
    result = _classify("sealed", "sealed", transition_evidence={"id": "ev"}, source="test")

    assert result["block_recommended"] is False


def test_observe_only_legacy_shortcuts() -> None:
    for source, target in (
        ("running", "committed"),
        ("unknown", "recovered"),
    ):
        result = _classify(source, target, transition_evidence={"id": "ev"}, source="test")
        assert result["enforcement_classification"] == "observe_only"
        assert result["observe_only"] is True
        assert result["safe_to_enforce"] is False


def test_missing_evidence_or_source_requires_review() -> None:
    missing_evidence = _classify("queued", "running", source="test")
    missing_source = _classify("queued", "running", transition_evidence={"id": "ev"})

    assert missing_evidence["review_required"] is True
    assert missing_source["review_required"] is True


def test_runtime_enforcement_readiness_payload_preserves_transition_payload() -> None:
    from core.runtime.runtime_enforcement_readiness import runtime_enforcement_readiness_payload

    payload = {
        "from_status": "verified",
        "to_status": "running",
        "allowed": False,
        "regression": True,
        "custom": "keep",
        "transition_evidence": {"id": "ev"},
        "source": "test",
    }
    result = runtime_enforcement_readiness_payload(payload)

    assert result["custom"] == "keep"
    assert result["block_recommended"] is True
    assert result["safe_to_enforce"] is True


def test_summarize_enforcement_readiness_counts() -> None:
    from core.runtime.runtime_enforcement_readiness import (
        runtime_enforcement_readiness_payload,
        summarize_enforcement_readiness,
    )

    items = [
        runtime_enforcement_readiness_payload(
            {
                "from_status": "sealed",
                "to_status": "running",
                "transition_evidence": {"id": "ev"},
                "source": "test",
            }
        ),
        runtime_enforcement_readiness_payload(
            {
                "from_status": "queued",
                "to_status": "running",
                "source": "test",
            }
        ),
        runtime_enforcement_readiness_payload(
            {
                "from_status": "running",
                "to_status": "committed",
                "transition_evidence": {"id": "ev"},
                "source": "test",
            }
        ),
    ]

    summary = summarize_enforcement_readiness(items)
    assert summary["total"] == 3
    assert summary["safe_to_enforce"] == 1
    assert summary["review_required"] == 1
    assert summary["block_recommended"] == 1
    assert summary["observe_only"] == 1


def test_canonical_transition_summary_exposes_enforcement_readiness() -> None:
    from core.runtime.runtime_status_transition import canonical_transition_summary

    summary = canonical_transition_summary(
        "verified",
        "running",
        source="test",
        metadata={"id": "meta"},
    )

    assert summary["block_recommended"] is True
    assert summary["safe_to_enforce"] is True
    assert summary["enforcement_reason"] == "canonical regression"


def test_runtime_surfaces_expose_enforcement_readiness() -> None:
    from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
    from core.runtime.runtime_kernel_state import RuntimeKernelStateMachine
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator
    from core.runtime.runtime_recovery_reconstruction import (
        build_runtime_recovery_reconstruction_contract,
    )
    from core.runtime.runtime_replay_engine import RuntimeReplayEngine
    from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator

    lifecycle = RuntimeLifecycleCoordinator()
    lifecycle.create_record(
        lifecycle_id="life-readiness",
        artifact_id="artifact-readiness",
        artifact_type="execution",
    )
    lifecycle_report = lifecycle.mark_active("life-readiness").to_metadata()
    kernel_report = RuntimeKernelStateMachine().transition("SCANNING", reason="scan").to_dict()

    transaction = RuntimeTransactionCoordinator()
    transaction.begin_transaction(transaction_id="tx-readiness")
    transaction_report = transaction.commit("tx-readiness").to_metadata()
    recovery_report = build_runtime_recovery_reconstruction_contract(
        source_transaction_id="tx-readiness",
        source_evidence_chain=[{"evidence_id": "ev-1"}],
        reconstruction_state="consistent",
    )

    manager = RuntimeExecutionSessionManager()
    manager.create_session("session-readiness", "life-readiness", replay_group="group-readiness")
    replay = RuntimeReplayEngine(manager).replay_session("replay-readiness", "session-readiness")

    for payload in (lifecycle_report, kernel_report, transaction_report, recovery_report):
        assert "enforcement_readiness" in payload
        assert "enforcement_reason" in payload
        assert "safe_to_enforce" in payload
        assert "review_required" in payload
        assert "block_recommended" in payload

    assert replay.enforcement_readiness
    assert hasattr(replay.records[0], "enforcement_readiness")
