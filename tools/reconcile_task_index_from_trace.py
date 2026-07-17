from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"finished", "failed", "blocked", "cancelled", "canceled", "done", "completed", "success"}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def _tasks_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return payload["tasks"]
    if isinstance(payload, list):
        return payload
    return []


def _latest_terminal_from_trace(trace_path: Path) -> dict[str, Any] | None:
    if not trace_path.exists():
        return None
    trace = _load_json(trace_path)
    events = trace.get("events") if isinstance(trace, dict) else []
    latest: dict[str, Any] | None = None
    for event in events or []:
        if not isinstance(event, dict):
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        status = str(data.get("status") or "").strip().lower()
        if status in TERMINAL_STATUSES:
            latest = data
    return latest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile ZERO workspace/tasks.json task status from per-task trace.json terminal events."
    )
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    tasks_json = workspace / "tasks.json"
    tasks_root = workspace / "tasks"

    if not tasks_json.exists():
        print(f"ERROR: missing tasks.json: {tasks_json}")
        return 2

    payload = _load_json(tasks_json)
    tasks = _tasks_list(payload)
    wanted = str(args.task_id or "").strip()

    changed = 0
    checked = 0

    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id") or task.get("id") or "").strip()
        if not task_id:
            continue
        if wanted and task_id != wanted:
            continue

        checked += 1
        trace_path = tasks_root / task_id / "trace.json"
        terminal = _latest_terminal_from_trace(trace_path)
        if not terminal:
            continue

        current_status = str(task.get("status") or "").strip().lower()
        terminal_status = str(terminal.get("status") or "").strip().lower()
        final_answer = str(terminal.get("final_answer") or "").strip()
        action = str(terminal.get("action") or "").strip()

        if current_status != terminal_status:
            print(f"{task_id}: {current_status or '<empty>'} -> {terminal_status} via trace action={action}")
            if args.apply:
                task["status"] = terminal_status
                if final_answer:
                    task["final_answer"] = final_answer
                    task["result_summary"] = final_answer
                task["trace_reconciled"] = True
                task["trace_reconcile_action"] = action
                changed += 1

    print(f"checked: {checked}")
    print(f"changed: {changed}")
    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}")

    if args.apply and changed:
        _write_json(tasks_json, payload)
        print(f"wrote: {tasks_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
