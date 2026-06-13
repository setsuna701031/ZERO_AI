from __future__ import annotations

import copy
import re
from typing import Any


def is_repo_edit_intent_candidate(text: str) -> bool:
    lowered = str(text or "").strip().lower().replace("\\", "/")
    if not lowered:
        return False
    has_target = "workspace/" in lowered or "core/" in lowered or "tests/" in lowered or ".py" in lowered
    has_edit = any(marker in lowered for marker in ("replace", " with ", "fix", "repair", "correct", "patch", "edit"))
    return has_target and has_edit


def _extract_target_path(text: str) -> str:
    match = re.search(r"((?:workspace|core|tests|services|cli)/[^\s'\"`,;:]+)", text.replace("\\", "/"))
    return match.group(1).strip().strip("'\"`.,;:") if match else ""


def build_forced_repo_edit_intent(goal: str, *, queued_status: str = "queued") -> dict[str, Any]:
    text = str(goal or "").strip()
    target_path = _extract_target_path(text)
    step = {
        "type": "code_chain_repair",
        "description": text,
        "target_path": target_path,
        "execution_intent_only": True,
        "mutation_executed": False,
    }
    forced = {
        "handled": True,
        "forced_route": True,
        "tool_name": "repo_edit_tool",
        "status": "intent_only",
        "execution_intent_only": True,
        "mutation_executed": False,
        "scheduler_required": True,
        "taskrunner_required": True,
        "step_executor_required": True,
        "governed_execution_required": True,
        "task_text": text,
        "target_path": target_path,
    }
    final_answer = "repo edit accepted as queued execution intent"
    return {
        "ok": True,
        "status": str(queued_status or "queued"),
        "mode": "forced_repo_edit_intent",
        "execution_intent_only": True,
        "mutation_executed": False,
        "forced": copy.deepcopy(forced),
        "forced_repo_edit": copy.deepcopy(forced),
        "final_answer": final_answer,
        "planner_result": {
            "ok": True,
            "planner_mode": "scheduler_forced_repo_edit_intent_v7_3_37",
            "intent": "repo_edit_execution_intent",
            "final_answer": final_answer,
            "steps": [step],
            "error": None,
            "meta": {
                "forced_route": True,
                "execution_intent_only": True,
                "mutation_executed": False,
                "authority_path": "AgentLoop/CreateTask -> Scheduler -> TaskRunner -> StepExecutor",
            },
            "forced_repo_edit": copy.deepcopy(forced),
        },
        "results": [],
        "execution_log": [
            {
                "type": "forced_repo_edit_intent",
                "tool": "repo_edit_tool",
                "status": "intent_only",
                "ok": True,
                "mutation_executed": False,
                "data": copy.deepcopy(forced),
            }
        ],
    }


__all__ = ["build_forced_repo_edit_intent", "is_repo_edit_intent_candidate"]
