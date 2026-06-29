from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import pytest

pytestmark = [pytest.mark.integration]




def _manager_with_session():
    from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

    manager = RuntimeExecutionSessionManager()
    manager.create_session(
        "session-replay-constitution",
        "life-replay-constitution",
        replay_group="group-replay-constitution",
        metadata={"operator": "test"},
    )
    manager.start_session("session-replay-constitution")
    manager.complete_session("session-replay-constitution", payload={"ok": True})
    return manager


def test_replay_continuity_is_preserved_and_non_blocking() -> None:
    from core.runtime.runtime_replay_engine import RuntimeReplayEngine

    replay = RuntimeReplayEngine(_manager_with_session()).replay_session(
        "replay-constitution",
        "session-replay-constitution",
    )

    assert replay.replay_id == "replay-constitution"
    assert replay.source_runtime_state_refs
    assert replay.transition_evidence
    assert replay.enforcement_visibility is True
    assert replay.enforcement_snapshot["schema"] == "runtime_enforcement_decision.v1"
    assert replay.replay_constitution_status == "canonical"
    assert replay.continuity_verified is True
    assert replay.block_recommended is False


def test_replay_lineage_and_snapshot_survive_serialization() -> None:
    from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
    from core.runtime.runtime_replay_engine import RuntimeReplayEngine

    manager = RuntimeExecutionSessionManager()
    manager.create_session("parent-session", "life-parent")
    manager.create_session(
        "child-session",
        "life-child",
        parent_session_id="parent-session",
    )

    replay = RuntimeReplayEngine(manager).replay_session("replay-child", "child-session")
    restored = json.loads(json.dumps(asdict(replay), sort_keys=True, default=str))

    assert restored["parent_replay_lineage"] == ["parent-session"]
    assert restored["source_runtime_state_refs"][0]["parent_session_id"] == "parent-session"
    assert restored["enforcement_snapshot"]["schema"] == "runtime_enforcement_decision.v1"
    assert restored["constitutional_continuity"]["classification"] == "canonical"


def test_replay_continuity_break_becomes_review_required() -> None:
    from core.runtime.runtime_replay_engine import replay_constitution_summary

    summary = replay_constitution_summary(
        replay_id="replay-review",
        parent_replay_lineage=[],
        source_runtime_state_refs=[],
        transition={"from_status": "replaying", "to_status": "replayed", "allowed": True},
        transition_evidence={},
        metadata={"parent_lineage_required": True},
    )

    assert summary["replay_constitution_status"] == "review_required"
    assert summary["review_required"] is True
    assert "missing_replay_evidence" in summary["continuity_break"]
    assert "missing_parent_lineage" in summary["continuity_break"]
    assert "missing_source_runtime_refs" in summary["continuity_break"]


def test_replay_corruption_and_loops_become_block_recommended() -> None:
    from core.runtime.runtime_replay_engine import replay_constitution_summary

    corrupted = replay_constitution_summary(
        replay_id="replay-corrupt",
        parent_replay_lineage=["ancestor", "ancestor"],
        source_runtime_state_refs=[{"source_session_id": "session-1"}],
        transition={"from_status": "replaying", "to_status": "replayed", "allowed": True},
        transition_evidence={"transition_evidence_id": "ev"},
    )
    loop = replay_constitution_summary(
        replay_id="replay-loop",
        parent_replay_lineage=["root", "replay-loop"],
        source_runtime_state_refs=[{"source_session_id": "session-1"}],
        transition={"from_status": "replaying", "to_status": "replayed", "allowed": True},
        transition_evidence={"transition_evidence_id": "ev"},
    )

    assert corrupted["replay_constitution_status"] == "block_recommended"
    assert "replay_lineage_corruption" in corrupted["continuity_break"]
    assert loop["replay_constitution_status"] == "block_recommended"
    assert "replay_loop" in loop["continuity_break"]


def test_sealed_resurrection_and_replayed_queue_reset_are_block_recommended() -> None:
    from core.runtime.runtime_replay_engine import replay_constitution_summary
    from core.runtime.runtime_status_transition import runtime_status_transition_payload

    sealed = replay_constitution_summary(
        replay_id="replay-sealed",
        parent_replay_lineage=[],
        source_runtime_state_refs=[{"source_session_id": "session-1"}],
        transition=runtime_status_transition_payload("sealed", "running", source="test"),
    )
    reset = replay_constitution_summary(
        replay_id="replay-reset",
        parent_replay_lineage=[],
        source_runtime_state_refs=[{"source_session_id": "session-1"}],
        transition=runtime_status_transition_payload("replayed", "queued", source="test"),
    )

    assert sealed["replay_constitution_status"] == "block_recommended"
    assert "sealed_active_replay_resurrection" in sealed["continuity_break"]
    assert reset["replay_constitution_status"] == "block_recommended"
    assert "replayed_queued_reset_loop" in reset["continuity_break"]


def test_forbidden_layers_do_not_import_replay_constitution_helpers() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = _forbidden_runtime_surfaces(root)
    markers = (
        "RuntimeEnforcementMode",
        "replay_constitution_summary",
        "replay_constitution_status",
    )

    for path in forbidden:
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source


def _forbidden_runtime_surfaces(root: Path) -> list[Path]:
    direct = [
        root / "core/tasks/scheduler.py",
        root / "core/agent/agent_loop.py",
        root / "core/runtime/step_executor.py",
        root / "core/runtime/repair_transaction_execution_bridge.py",
        root / "app.py",
        root / "services/system_boot.py",
    ]
    directories = [root / "tools", root / "core/tools", root / "ui"]
    paths = [path for path in direct if path.exists()]
    for directory in directories:
        if directory.exists():
            paths.extend(
                path
                for path in directory.rglob("*.py")
                if "__pycache__" not in path.parts
            )
    return paths
