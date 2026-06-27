from __future__ import annotations

import os
from typing import Any, Dict


def handle_simple_noop_step(step: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "type": "noop",
        "message": str(step.get("message") or "noop ok"),
    }


def handle_simple_ensure_file_step(
    scheduler,
    *,
    step: Dict[str, Any],
    task_dir: str,
    step_scope: str,
    guard_result: Dict[str, Any],
) -> Dict[str, Any]:
    raw_path = str(step.get("path") or "").strip()
    if not raw_path:
        raise ValueError("ensure_file step missing path")

    if str(step_scope or "").strip().lower() == "shared":
        full_path = scheduler._resolve_step_path(
            raw_path=raw_path,
            task_dir=task_dir,
            shared_dir=scheduler.shared_dir,
            scope="shared",
        )
    else:
        full_path = scheduler._resolve_guard_target_path(
            raw_path=raw_path,
            task_dir=task_dir,
            scope=step_scope,
            resolved_path=str(guard_result.get("resolved_path") or ""),
        )

    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    created = False
    if not os.path.exists(full_path):
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("")
        created = True

    return {
        "type": "ensure_file",
        "path": raw_path,
        "full_path": full_path,
        "scope": step_scope,
        "created": created,
        "preserved_existing": not created,
    }
