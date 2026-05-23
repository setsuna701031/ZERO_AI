from __future__ import annotations

import pytest

from core.runtime.snapshot_loader.replay_governance_envelope import (
    build_replay_governance_event,
    build_replay_governance_summary,
    evaluate_replay_governance_event,
)


def test_build_replay_governance_event_contract() -> None:
    event = build_replay_governance_event(
        action="readonly_execution",
        payload={"task": "inspect"},
        replay_id="replay-1",
        sequence=3,
        source="test_replay",
    )

    assert event == {
        "replay_id": "replay-1",
        "sequence": 3,
        "source": "test_replay",
        "action": "readonly_execution",
        "payload": {"task": "inspect"},
    }


def test_build_replay_governance_event_rejects_empty_action() -> None:
    with pytest.raises(ValueError):
        build_replay_governance_event(action="   ")


def test_build_replay_governance_event_rejects_negative_sequence() -> None:
    with pytest.raises(ValueError):
        build_replay_governance_event(
            action="readonly_execution",
            sequence=-1,
        )


def test_evaluate_replay_governance_event_allows_readonly() -> None:
    event = build_replay_governance_event(
        action="readonly_execution",
        payload={"task": "inspect"},
        replay_id="replay-allow",
        sequence=0,
    )

    result = evaluate_replay_governance_event(event)

    assert result["ok"] is True
    assert result["status"] == "allowed_no_handler"
    assert result["replay_id"] == "replay-allow"
    assert result["sequence"] == 0
    assert result["action"] == "readonly_execution"
    assert result["governance"]["allowed"] is True


def test_evaluate_replay_governance_event_blocks_mutation_runtime() -> None:
    event = build_replay_governance_event(
        action="mutation_runtime",
        payload={"target": "core/runtime/example.py"},
        replay_id="replay-block",
        sequence=1,
    )

    result = evaluate_replay_governance_event(event)

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["replay_id"] == "replay-block"
    assert result["sequence"] == 1
    assert result["action"] == "mutation_runtime"
    assert result["governance"]["allowed"] is False


def test_evaluate_replay_governance_event_blocks_patch_apply() -> None:
    event = build_replay_governance_event(
        action="patch_apply",
        payload={"patch": "diff --git ..."},
        replay_id="replay-block",
        sequence=2,
    )

    result = evaluate_replay_governance_event(event)

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["action"] == "patch_apply"
    assert result["governance"]["allowed"] is False


def test_evaluate_replay_governance_event_blocks_unrestricted_shell() -> None:
    event = build_replay_governance_event(
        action="unrestricted_shell",
        payload={"command": "dir"},
        replay_id="replay-block",
        sequence=3,
    )

    result = evaluate_replay_governance_event(event)

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["action"] == "unrestricted_shell"
    assert result["governance"]["allowed"] is False


def test_evaluate_replay_governance_event_rejects_bad_payload() -> None:
    with pytest.raises(TypeError):
        evaluate_replay_governance_event(
            {
                "replay_id": "bad-payload",
                "sequence": 0,
                "source": "test",
                "action": "readonly_execution",
                "payload": ["not", "mapping"],
            }
        )


def test_replay_governance_summary_contract() -> None:
    events = [
        build_replay_governance_event(
            action="readonly_execution",
            replay_id="replay-summary",
            sequence=0,
        ),
        build_replay_governance_event(
            action="mutation_runtime",
            replay_id="replay-summary",
            sequence=1,
        ),
        build_replay_governance_event(
            action="patch_apply",
            replay_id="replay-summary",
            sequence=2,
        ),
        build_replay_governance_event(
            action="unrestricted_shell",
            replay_id="replay-summary",
            sequence=3,
        ),
    ]

    summary = build_replay_governance_summary(events)

    assert summary["replay_governance"] == "snapshot_loader_replay_governance_envelope"
    assert summary["event_count"] == 4
    assert summary["allowed_actions"] == ["readonly_execution"]
    assert summary["blocked_actions"] == [
        "mutation_runtime",
        "patch_apply",
        "unrestricted_shell",
    ]
    assert len(summary["events"]) == 4


def test_replay_governance_summary_rejects_non_list_events() -> None:
    with pytest.raises(TypeError):
        build_replay_governance_summary(("not", "a", "list"))  # type: ignore[arg-type]