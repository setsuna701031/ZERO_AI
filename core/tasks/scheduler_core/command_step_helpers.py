from __future__ import annotations

from typing import Any, Dict, Optional

from .command_step_handlers import handle_command_step, handle_run_python_step


def execute_command_like_step(
    scheduler,
    step: Dict[str, Any],
    step_type: str,
    task_dir: str,
    step_scope: str,
) -> Optional[Dict[str, Any]]:
    if step_type == "command":
        return handle_command_step(
            scheduler,
            step,
            task_dir=task_dir,
            step_scope=step_scope,
        )

    if step_type == "run_python":
        return handle_run_python_step(
            scheduler,
            step,
            task_dir=task_dir,
            step_scope=step_scope,
        )

    return None
