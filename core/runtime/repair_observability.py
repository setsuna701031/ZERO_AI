from __future__ import annotations

import copy
from typing import Any, Dict


def build_repair_chain_id(
    *,
    task: Dict[str, Any],
    source_path: str,
    step_index: int,
    current_tick: int,
) -> str:
    """Build a compact, deterministic id for one repair decision chain."""

    task = task if isinstance(task, dict) else {}
    task_id = str(task.get("task_id") or task.get("id") or task.get("task_name") or "task").strip()
    if not task_id:
        task_id = "task"

    source = str(source_path or "unknown").replace("\\", "/").replace("/", "_").replace(":", "")
    if not source:
        source = "unknown"

    return f"repair_{task_id}_{source}_step_{int(step_index)}_tick_{int(current_tick)}"


def build_repair_origin_step(
    *,
    step: Dict[str, Any] | None,
    step_index: int,
    source_path: str,
) -> Dict[str, Any]:
    step = step if isinstance(step, dict) else {}
    return {
        "step_index": int(step_index),
        "step_id": str(step.get("id") or ""),
        "step_type": str(step.get("type") or ""),
        "source_path": str(source_path or ""),
    }


def build_repair_observability(
    *,
    task: Dict[str, Any] | None,
    step: Dict[str, Any] | None,
    source_path: str,
    step_index: int,
    current_tick: int,
    policy_decision: Dict[str, Any],
    repair_chain_id: str = "",
) -> Dict[str, Any]:
    """Build durable metadata for reconstructing an autonomous repair decision.

    This function is intentionally pure and side-effect free.  TaskRunner owns
    persistence and trace emission; this module only formats compact metadata.
    """

    decision = copy.deepcopy(policy_decision) if isinstance(policy_decision, dict) else {
        "allow": False,
        "action": "fail",
        "reason": "invalid repair policy decision",
    }

    chain_id = str(repair_chain_id or "").strip() or build_repair_chain_id(
        task=task if isinstance(task, dict) else {},
        source_path=source_path,
        step_index=step_index,
        current_tick=current_tick,
    )

    reason = str(decision.get("reason") or "")
    return {
        "repair_chain_id": chain_id,
        "repair_origin_step": build_repair_origin_step(
            step=step,
            step_index=step_index,
            source_path=source_path,
        ),
        "repair_policy_decision": decision,
        "repair_risk_level": str(decision.get("risk_level") or ""),
        "repair_block_reason": reason,
        "repair_quarantine_reason": reason if bool(decision.get("quarantine")) else "",
        "repair_depth": decision.get("current_repair_depth", 0),
        "max_repair_depth": decision.get("max_repair_depth", 1),
    }
