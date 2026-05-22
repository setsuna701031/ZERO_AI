from __future__ import annotations


def _continuation(reason: str, *, terminal: bool = False, classification: str = "review_required") -> dict:
    return {
        "governed_continuation": True,
        "continuation_state": "terminal_constitutional_block" if terminal else "governed_continuation_boundary",
        "continuation_reason": reason,
        "continuation_cycle_id": "cycle-self-repair",
        "governed_resume_candidate": not terminal,
        "governed_recovery_candidate": not terminal,
        "governed_replay_candidate": not terminal,
        "terminal_constitutional_boundary": terminal,
        "constitutional_enforcement_snapshot": {
            "schema": "runtime_enforcement_decision.v1",
            "classification": "block_recommended" if terminal else classification,
            "safe_to_enforce": terminal,
            "reason": reason,
        },
        "replay_continuity_summary": {"replay_id": "replay-self-repair"},
        "recovery_continuity_summary": {"recovery_id": "recovery-self-repair"},
    }


def test_recoverable_constitutional_interruption_becomes_repair_review_required() -> None:
    import core.tasks.scheduler as scheduler_module

    summary = scheduler_module._zero_v7334_governed_self_repair_summary(
        {"governed_continuation": _continuation("missing_replay_evidence")}
    )

    assert summary["self_repair_state"] == "repair_review_required"
    assert summary["self_repair_candidate"] is True
    assert summary["self_repair_review_required"] is True
    assert summary["self_repair_bridge_ready"] is False


def test_terminal_constitutional_boundary_becomes_repair_blocked_terminal() -> None:
    import core.tasks.scheduler as scheduler_module

    summary = scheduler_module._zero_v7334_governed_self_repair_summary(
        {"governed_continuation": _continuation("sealed_resurrection_attempt", terminal=True)}
    )

    assert summary["self_repair_state"] == "repair_blocked_terminal"
    assert summary["self_repair_terminal_block"] is True
    assert summary["self_repair_legality"] == "blocked"


def test_self_repair_metadata_survives_agent_loop_continuation_cycle() -> None:
    from core.agent.agent_loop import AgentLoop

    class Runner:
        def run_task(self, **_kwargs):
            return {
                "ok": True,
                "status": "running",
                "governed_continuation": _continuation("missing_recovery_evidence"),
                "runtime_state": {
                    "governed_continuation": _continuation("missing_recovery_evidence"),
                },
            }

    result = AgentLoop(task_runner=Runner()).run_task_loop(
        {"task_id": "self-repair-cycle", "status": "running", "steps": [{"type": "x"}]},
        current_tick=1,
    )

    assert result["task"]["governed_self_repair"]["self_repair_state"] == "repair_review_required"
    assert result["execution"]["governed_self_repair"]["self_repair_lineage"]["recovery_continuity_summary"]["recovery_id"] == "recovery-self-repair"


def test_replay_and_recovery_snapshots_preserved_in_self_repair_summary() -> None:
    import core.tasks.scheduler as scheduler_module

    summary = scheduler_module._zero_v7334_governed_self_repair_summary(
        {"governed_continuation": _continuation("missing_replay_evidence")}
    )

    lineage = summary["self_repair_lineage"]
    assert lineage["replay_continuity_summary"]["replay_id"] == "replay-self-repair"
    assert lineage["recovery_continuity_summary"]["recovery_id"] == "recovery-self-repair"
    assert summary["self_repair_boundary"]["enforcement_snapshot"]["schema"] == "runtime_enforcement_decision.v1"


def test_normal_operational_failure_remains_normal_failure() -> None:
    import core.tasks.scheduler as scheduler_module

    summary = scheduler_module._zero_v7334_governed_self_repair_summary(
        {"ok": False, "error": "ordinary failure"}
    )

    assert summary["self_repair_state"] == "no_repair"
    assert summary["governed_self_repair"] is False
