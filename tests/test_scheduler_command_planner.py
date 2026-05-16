from __future__ import annotations

from core.tasks.scheduler import Scheduler
from core.tasks.scheduler_core.command_planner import try_plan_command


def test_try_plan_command_ignores_non_command_inline_task_goal() -> None:
    result = try_plan_command(
        "smoke task :: step=write_file:shared/scheduler_smoke.txt|hello scheduler "
        ":: step=verify:contains=hello"
    )

    assert result is None


def test_try_plan_command_parses_supported_command_prefixes() -> None:
    assert try_plan_command("run echo hello") == {
        "type": "command",
        "command": "echo hello",
    }
    assert try_plan_command("command: python script.py") == {
        "type": "command",
        "command": "python script.py",
    }
    assert try_plan_command("powershell Get-ChildItem") == {
        "type": "command",
        "command": "powershell Get-ChildItem",
    }


def test_scheduler_try_plan_command_wrapper_uses_helper_without_regex_error() -> None:
    scheduler = Scheduler.__new__(Scheduler)

    assert scheduler._try_plan_command("??? echo hello") is None
    assert scheduler._try_plan_command("run echo hello") == {
        "type": "command",
        "command": "echo hello",
    }
