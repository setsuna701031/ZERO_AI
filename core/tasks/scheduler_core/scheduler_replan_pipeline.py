from __future__ import annotations

import copy
from typing import Any, Dict, List


def apply_replan_task(scheduler: Any, task: Dict[str, Any]) -> Dict[str, Any]:
    result = scheduler._try_replan_task(task, apply=True)
    if isinstance(result, dict):
        result["mode"] = "replan_apply"
        result["approved"] = bool(result.get("replanned"))
        result["submitted"] = bool(result.get("replanned"))
        result["queued"] = str(task.get("status") or "").strip().lower() == "queued"
        result["ran"] = False
        return result

    return {
        "ok": False,
        "mode": "replan_apply",
        "approved": False,
        "submitted": False,
        "queued": False,
        "ran": False,
        "error": "invalid apply result",
    }


def preview_replan_task(scheduler: Any, task: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(task, dict):
        return {
            "ok": False,
            "mode": "replan_preview",
            "error": "invalid task payload",
            "would_replan": False,
            "dry_run": True,
            "submitted": False,
            "ran": False,
        }

    preview_task = copy.deepcopy(task)
    original_steps = copy.deepcopy(preview_task.get("steps", [])) if isinstance(preview_task.get("steps"), list) else []
    original_fingerprint = scheduler._fingerprint_steps(original_steps)
    budget = scheduler._replan_budget_payload(preview_task)

    result = scheduler._try_replan_task(preview_task)
    if not isinstance(result, dict):
        result = {
            "ok": False,
            "replanned": False,
            "decision": "error",
            "summary": "invalid replan preview result",
        }

    preview_steps: List[Dict[str, Any]] = []
    raw_replan = result.get("raw_replan_result")
    plan = raw_replan.get("plan") if isinstance(raw_replan, dict) else None
    if isinstance(plan, dict) and isinstance(plan.get("steps"), list):
        preview_steps = copy.deepcopy(plan.get("steps"))
    elif bool(result.get("replanned")) and isinstance(preview_task.get("steps"), list):
        preview_steps = copy.deepcopy(preview_task.get("steps"))

    preview_fingerprint = scheduler._fingerprint_steps(preview_steps) if preview_steps else ""

    return {
        "ok": bool(result.get("ok", False)),
        "mode": "replan_preview",
        "dry_run": True,
        "submitted": False,
        "ran": False,
        "task_id": str(preview_task.get("task_id") or preview_task.get("task_name") or ""),
        "status": str(task.get("status") or ""),
        "can_replan": bool(result.get("would_replan") or result.get("replanned")),
        "would_replan": bool(result.get("would_replan") or result.get("replanned")),
        "decision": str(result.get("decision") or ""),
        "summary": str(result.get("summary") or ""),
        "repairable": result.get("repairable", None),
        "failed_step_type": str(result.get("failed_step_type") or scheduler._get_failed_step_type(preview_task)),
        "replan_count": int(result.get("replan_count", budget["replan_count"]) or 0),
        "max_replans": int(result.get("max_replans", budget["max_replans"]) or 0),
        "remaining_replans": int(result.get("remaining_replans", budget["remaining"]) or 0),
        "original_plan_fingerprint": original_fingerprint,
        "preview_plan_fingerprint": preview_fingerprint,
        "same_plan": bool(preview_fingerprint and preview_fingerprint == original_fingerprint),
        "preview_steps": preview_steps,
        "preview_step_count": len(preview_steps),
        "replan_trace": copy.deepcopy(preview_task.get("replan_trace", [])),
        "raw_replan_result": copy.deepcopy(raw_replan) if isinstance(raw_replan, dict) else None,
        "error": result.get("error"),
    }
