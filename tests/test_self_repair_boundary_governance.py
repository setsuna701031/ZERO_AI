from __future__ import annotations

from pathlib import Path


def _terminal_task() -> dict:
    return {
        "task_id": "terminal-self-repair",
        "status": "failed",
        "governed_continuation": {
            "governed_continuation": True,
            "continuation_state": "terminal_constitutional_block",
            "continuation_reason": "replay_lineage_corruption",
            "terminal_constitutional_boundary": True,
            "constitutional_enforcement_snapshot": {
                "classification": "block_recommended",
                "safe_to_enforce": True,
                "reason": "replay_lineage_corruption",
            },
        },
    }


def test_scheduler_does_not_blind_repair_terminal_self_repair_block(tmp_path: Path) -> None:
    from core.tasks.scheduler import Scheduler

    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))
    repairable, reason = scheduler._is_repairable_failure(_terminal_task())

    assert repairable is False
    assert "self-repair block" in reason


def test_agent_loop_does_not_auto_bypass_or_auto_mutate_terminal_self_repair() -> None:
    from core.agent.agent_loop import AgentLoop

    class Runner:
        def __init__(self) -> None:
            self.calls = 0

        def run_task(self, **_kwargs):
            self.calls += 1
            return {
                "ok": False,
                "status": "failed",
                "runtime_state": _terminal_task(),
                "governed_continuation": _terminal_task()["governed_continuation"],
            }

    runner = Runner()
    result = AgentLoop(task_runner=runner).run_task_loop(
        {"task_id": "agent-terminal-self-repair", "status": "running", "steps": [{"type": "x"}]},
        current_tick=1,
    )

    assert runner.calls == 1
    assert result["task"]["self_repair_state"] == "repair_blocked_terminal"
    assert result["task"]["self_repair_bridge_ready"] is False
    assert result["task"]["replan_blocked_reason"] == "terminal_constitutional_boundary"


def test_advisory_failed_verification_becomes_repair_candidate() -> None:
    import core.tasks.scheduler as scheduler_module

    summary = scheduler_module._zero_v7334_governed_self_repair_summary(
        {
            "ok": False,
            "verification_passed": False,
            "runtime_execution_result": {
                "metadata": {
                    "constitutional_activation": True,
                    "constitutional_activation_mode": "advisory",
                    "constitutional_activation_reason": "advisory verification failed",
                    "constitutional_enforcement_snapshot": {
                        "classification": "observe_only",
                        "safe_to_enforce": False,
                        "reason": "advisory verification failed",
                    },
                }
            },
        }
    )

    assert summary["self_repair_state"] == "repair_candidate"
    assert summary["self_repair_candidate"] is True
    assert summary["self_repair_bridge_ready"] is False


def test_no_repair_bridge_ui_tools_app_system_boot_coupling_added() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "app.py", root / "services/system_boot.py"]
    for directory in (root / "tools", root / "core/tools", root / "ui"):
        if directory.exists():
            paths.extend(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)

    markers = (
        "_zero_v7334_governed_self_repair_summary",
        "self_repair_bridge_ready",
        "repair_ready_for_guarded_bridge",
    )
    for path in paths:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source
