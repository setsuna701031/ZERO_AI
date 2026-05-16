from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def extract_effective_status_and_answer(
    original_task: Optional[Dict[str, Any]],
    refreshed_task: Optional[Dict[str, Any]],
    runner_result: Optional[Dict[str, Any]],
) -> Tuple[str, Any]:
    candidates: List[Dict[str, Any]] = []

    if isinstance(runner_result, dict):
        candidates.append(runner_result)
    if isinstance(refreshed_task, dict):
        candidates.append(refreshed_task)
    if isinstance(original_task, dict):
        candidates.append(original_task)

    status = ""
    final_answer: Any = ""

    for source in candidates:
        source_status = str(source.get("status") or "").strip().lower()
        if source_status:
            status = source_status
            break

    for source in candidates:
        if "final_answer" in source:
            value = source.get("final_answer")
            if value not in (None, ""):
                final_answer = value
                break

    return status, final_answer
