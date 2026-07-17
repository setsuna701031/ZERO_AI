from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = [pytest.mark.integration]




def _continuation(reason: str, *, terminal: bool = False, classification: str = "review_required") -> dict:
    return {
        "governed_continuation": True,
        "continuation_state": "terminal_constitutional_block" if terminal else "governed_continuation_boundary",
        "continuation_reason": reason,
        "continuation_cycle_id": "cycle-bridge",
        "continuation_parent": "cycle-parent",
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
        "replay_continuity_summary": {"replay_id": "replay-bridge"},
        "recovery_continuity_summary": {"recovery_id": "recovery-bridge"},
    }


def _bridge_candidate(reason: str = "missing_replay_evidence") -> dict:
    import core.tasks.scheduler as scheduler_module

    payload = {"governed_continuation": _continuation(reason)}
    scheduler_module._zero_v7334_attach_self_repair_summary(payload)
    scheduler_module._zero_v7335_attach_controlled_mutation_bridge(payload)
    return payload


def test_repair_candidate_can_become_bridge_ready_for_review() -> None:
    import core.tasks.scheduler as scheduler_module

    summary = scheduler_module._zero_v7335_controlled_mutation_bridge_summary(
        _bridge_candidate("missing_replay_evidence")
    )

    assert summary["mutation_bridge_state"] == "bridge_ready_for_review"
    assert summary["mutation_bridge_eligible"] is True
    assert summary["mutation_bridge_requires_review"] is True
    assert summary["bridge_verification_required"] is True
    assert summary["bridge_rollback_required"] is True


def test_repair_review_required_can_become_bridge_ready_for_review() -> None:
    import core.tasks.scheduler as scheduler_module

    payload = {"governed_continuation": _continuation("missing_recovery_evidence")}
    summary = scheduler_module._zero_v7335_controlled_mutation_bridge_summary(payload)

    assert summary["mutation_bridge_state"] == "bridge_ready_for_review"
    assert summary["bridge_legality"] == "review_required"


def test_terminal_repair_block_cannot_enter_bridge() -> None:
    import core.tasks.scheduler as scheduler_module

    payload = {"governed_continuation": _continuation("sealed_resurrection", terminal=True)}
    summary = scheduler_module._zero_v7335_controlled_mutation_bridge_summary(payload)

    assert summary["mutation_bridge_state"] == "bridge_blocked_terminal"
    assert summary["mutation_bridge_eligible"] is False
    assert summary["bridge_terminality"] == "terminal"


def test_missing_enforcement_snapshot_blocks_bridge_eligibility() -> None:
    import core.tasks.scheduler as scheduler_module

    payload = _bridge_candidate()
    payload["governed_self_repair"]["self_repair_boundary"]["enforcement_snapshot"] = {}
    payload.pop("governed_continuation", None)

    summary = scheduler_module._zero_v7335_controlled_mutation_bridge_summary(payload)

    assert summary["mutation_bridge_state"] == "bridge_blocked_missing_enforcement_snapshot"
    assert summary["mutation_bridge_eligible"] is False


def test_missing_continuation_lineage_blocks_bridge_eligibility() -> None:
    import core.tasks.scheduler as scheduler_module

    payload = _bridge_candidate()
    payload["governed_self_repair"]["self_repair_lineage"] = {}

    summary = scheduler_module._zero_v7335_controlled_mutation_bridge_summary(payload)

    assert summary["mutation_bridge_state"] == "bridge_blocked_missing_continuation_lineage"
    assert summary["mutation_bridge_eligible"] is False


def test_scheduler_preserves_bridge_eligibility_metadata() -> None:
    import core.tasks.scheduler as scheduler_module

    task = {"task_id": "bridge-scheduler", "status": "review_required"}
    result = _bridge_candidate()
    scheduler_module._zero_v7335_attach_controlled_mutation_bridge(result)
    scheduler_module._zero_v7335_attach_controlled_mutation_bridge(task | result)

    assert result["mutation_bridge_eligible"] is True
    assert result["mutation_bridge_enforcement_snapshot"]["schema"] == "runtime_enforcement_decision.v1"
    assert result["mutation_bridge_replay_snapshot"]["replay_id"] == "replay-bridge"
    assert result["mutation_bridge_recovery_snapshot"]["recovery_id"] == "recovery-bridge"


def test_no_ui_tools_app_system_boot_coupling_added() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "app.py", root / "services/system_boot.py"]
    for directory in (root / "tools", root / "core/tools", root / "ui"):
        if directory.exists():
            paths.extend(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)

    markers = (
        "_zero_v7335_controlled_mutation_bridge_summary",
        "mutation_bridge_eligible",
        "controlled_mutation_bridge_review_required",
    )
    for path in paths:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source
