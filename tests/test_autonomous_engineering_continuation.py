from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = [pytest.mark.integration]




def _snapshot(classification: str, *, safe: bool = False, reason: str = "") -> dict:
    return {
        "schema": "runtime_enforcement_decision.v1",
        "classification": classification,
        "safe_to_enforce": safe,
        "reason": reason or classification,
        "would_block": classification == "block_recommended",
    }


def _metadata(classification: str, *, blocked: bool, safe: bool, reason: str) -> dict:
    return {
        "constitutional_activation": True,
        "constitutional_activation_mode": "selective_activation" if blocked else "advisory",
        "constitutional_activation_reason": reason,
        "constitutional_blocked": blocked,
        "constitutional_enforcement_snapshot": _snapshot(classification, safe=safe, reason=reason),
        "constitutional_continuity_status": classification,
        "constitutional_continuity": {
            "kind": "runtime_replay_constitution",
            "replay_id": "replay-continuation",
            "parent_replay_lineage": ["parent-replay"],
            "source_runtime_state_refs": [{"source_session_id": "session-continuation"}],
        },
        "replay_constitution_status": classification,
    }


def _runner_result(metadata: dict) -> dict:
    step = {
        "ok": not metadata.get("constitutional_blocked"),
        "runtime_execution_result": {"metadata": metadata},
    }
    return {
        "ok": not metadata.get("constitutional_blocked"),
        "status": "failed" if metadata.get("constitutional_blocked") else "running",
        "last_step_result": step,
        "runtime_state": {"last_step_result": step, "results": [step]},
    }


class RecoverableRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run_task(self, **_kwargs):
        self.calls += 1
        return _runner_result(
            _metadata(
                "review_required",
                blocked=False,
                safe=False,
                reason="missing_replay_evidence",
            )
        )


class TerminalRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run_task(self, **_kwargs):
        self.calls += 1
        return _runner_result(
            _metadata(
                "block_recommended",
                blocked=True,
                safe=True,
                reason="sealed_resurrection_attempt",
            )
        )


def test_governed_continuation_survives_loop_cycles() -> None:
    from core.agent.agent_loop import AgentLoop

    runner = RecoverableRunner()
    loop = AgentLoop(task_runner=runner)
    result = loop.run_task_until_terminal(
        {"task_id": "continuation-cycle", "status": "running", "steps": [{"type": "x"}]},
        max_cycles=2,
    )

    assert runner.calls >= 1
    assert result["task"]["governed_continuation"]["governed_resume_candidate"] is True
    assert result["last_result"]["execution"]["governed_resume_candidate"] is True


def test_constitutional_interruption_metadata_survives_continuation() -> None:
    from core.agent.agent_loop import AgentLoop

    result = AgentLoop(task_runner=RecoverableRunner()).run_task_loop(
        {"task_id": "metadata-survives", "status": "running", "steps": [{"type": "x"}]},
        current_tick=1,
    )

    summary = result["task"]["governed_continuation"]
    assert summary["continuation_reason"] == "missing_replay_evidence"
    assert summary["constitutional_enforcement_snapshot"]["classification"] == "review_required"
    assert summary["replay_continuity_summary"]["replay_id"] == "replay-continuation"


def test_recoverable_interruptions_continue_safely() -> None:
    from core.agent.agent_loop import AgentLoop

    result = AgentLoop(task_runner=RecoverableRunner()).run_task_loop(
        {"task_id": "recoverable", "status": "running", "steps": [{"type": "x"}]},
        current_tick=1,
    )

    assert result["task"]["governed_resume_candidate"] is True
    assert result["task"]["governed_recovery_candidate"] is True
    assert result["task"].get("replan_blocked_reason", "") != "terminal_constitutional_boundary"


def test_terminal_constitutional_boundaries_stop_continuation() -> None:
    from core.agent.agent_loop import AgentLoop

    result = AgentLoop(task_runner=TerminalRunner()).run_task_loop(
        {"task_id": "terminal", "status": "running", "steps": [{"type": "x"}]},
        current_tick=1,
    )

    assert result["task"]["governed_continuation"]["terminal_constitutional_boundary"] is True
    assert result["task"]["governed_continuation"]["terminal_constitutional_boundary"] is True
    assert result["next_action"] == "wait_for_external_event"


def test_agent_loop_does_not_recursively_replan_blocked_continuation() -> None:
    from core.agent.agent_loop import AgentLoop

    result = AgentLoop(task_runner=TerminalRunner()).run_task_loop(
        {
            "task_id": "no-recursive-replan",
            "status": "running",
            "steps": [{"type": "x"}],
            "max_replans": 5,
            "replan_count": 0,
        },
        current_tick=1,
    )

    assert result["loop_decision"] == "wait"
    assert result["task"]["replan_count"] == 0
    assert result["task"]["governed_continuation"]["continuation_legality"] == "terminal"


def test_no_ui_tools_app_system_boot_coupling_added_for_continuation() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "app.py", root / "services/system_boot.py"]
    for directory in (root / "tools", root / "core/tools", root / "ui"):
        if directory.exists():
            paths.extend(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)

    markers = (
        "_zero_v7333_governed_continuation_summary",
        "governed_continuation_boundary",
        "terminal_constitutional_boundary",
    )
    for path in paths:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source
