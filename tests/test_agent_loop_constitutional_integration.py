from __future__ import annotations

from pathlib import Path


def _constitutional_runner_result() -> dict:
    snapshot = {
        "schema": "runtime_enforcement_decision.v1",
        "mode": "dry_run",
        "classification": "block_recommended",
        "safe_to_enforce": True,
        "reason": "sealed state is terminal",
        "would_block": True,
    }
    metadata = {
        "constitutional_activation": True,
        "constitutional_activation_mode": "selective_activation",
        "constitutional_activation_reason": "sealed_resurrection_attempt",
        "constitutional_blocked": True,
        "constitutional_enforcement_snapshot": snapshot,
        "constitutional_continuity_status": "block_recommended",
    }
    step_result = {
        "ok": False,
        "blocked": True,
        "runtime_execution_result": {
            "ok": False,
            "blocked": True,
            "metadata": metadata,
        },
    }
    return {
        "ok": False,
        "action": "step_failed",
        "status": "failed",
        "last_result": step_result,
        "last_step_result": step_result,
        "runtime_state": {
            "status": "failed",
            "last_step_result": step_result,
            "results": [step_result],
            "step_results": [step_result],
        },
    }


class ConstitutionalRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run_task(self, **_kwargs):
        self.calls += 1
        return _constitutional_runner_result()


class SuccessRunner:
    def run_task(self, **_kwargs):
        return {
            "ok": True,
            "action": "step_completed",
            "status": "running",
            "last_result": {"ok": True, "message": "ok"},
            "runtime_state": {
                "status": "running",
                "results": [{"ok": True, "message": "ok"}],
                "last_step_result": {"ok": True, "message": "ok"},
            },
        }


def test_agent_loop_recognizes_constitutional_block() -> None:
    from core.agent.agent_loop import AgentLoop

    runner = ConstitutionalRunner()
    loop = AgentLoop(task_runner=runner)
    result = loop.run_task_loop(
        task={"task_id": "agent-constitutional", "status": "running", "steps": [{"type": "x"}]},
        current_tick=1,
    )

    assert runner.calls == 1
    assert result["status"] in {"blocked", "review_required"}
    assert result["agent_action"] in {"governed_constitutional_boundary", "await_external_decision"}
    assert result["task"]["constitutional_boundary"]["type"] == "constitutional_execution_boundary"
    assert result["blocked_reason"] == "sealed_resurrection_attempt"
    assert result["execution"]["governed_runtime_boundary"] is True
    assert result["execution"]["constitutional_blocked"] is True


def test_agent_loop_does_not_replan_into_same_blocked_step() -> None:
    from core.agent.agent_loop import AgentLoop

    loop = AgentLoop(task_runner=ConstitutionalRunner())
    result = loop.run_task_loop(
        task={
            "task_id": "agent-no-replan",
            "status": "running",
            "steps": [{"type": "x"}],
            "max_replans": 3,
            "replan_count": 0,
        },
        current_tick=1,
    )

    assert result["loop_decision"] == "wait"
    assert result["next_action"] == "wait_for_external_event"
    assert result["task"]["replan_blocked_reason"] == "constitutional_boundary"
    assert result["task"].get("replan_count", 0) == 0


def test_agent_loop_reports_governed_boundary_state() -> None:
    from core.agent.agent_loop import AgentLoop

    loop = AgentLoop(task_runner=ConstitutionalRunner())
    result = loop.run_task_loop(
        task={"task_id": "agent-boundary", "status": "running", "steps": [{"type": "x"}]},
        current_tick=1,
    )

    boundary = result["task"]["constitutional_boundary"]
    assert boundary["type"] == "constitutional_execution_boundary"
    assert boundary["constitutional_blocked"] is True
    assert boundary["constitutional_enforcement_snapshot"]["classification"] == "block_recommended"
    assert result["task"]["requires_review"] is True


def test_agent_loop_normal_success_path_unchanged() -> None:
    from core.agent.agent_loop import AgentLoop

    loop = AgentLoop(task_runner=SuccessRunner())
    result = loop.run_task_loop(
        task={"task_id": "agent-ok", "status": "running", "steps": [{"type": "x"}]},
        current_tick=1,
    )

    assert result["status"] == "running"
    assert result["execution"]["ok"] is True
    assert "constitutional_boundary" not in result["task"]


def test_agent_loop_no_ui_tools_app_system_boot_coupling_added() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "app.py", root / "services/system_boot.py"]
    for directory in (root / "tools", root / "core/tools", root / "ui"):
        if directory.exists():
            paths.extend(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)

    markers = (
        "_zero_v7332_agent_observe_and_record_loop_decision",
        "governed_constitutional_boundary",
        "constitutional_execution_boundary",
    )
    for path in paths:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source
