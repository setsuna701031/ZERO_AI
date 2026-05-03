from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from core.audit.task_audit import load_audit_events


PROBLEM_STATUSES = {"failed", "blocked", "error", "denied", "deny"}


def query_events_by_task_id(workspace_root: str, task_id: str) -> List[Dict[str, Any]]:
    return load_audit_events(workspace_root, task_id=str(task_id or "").strip())


def query_events_by_trace_id(workspace_root: str, trace_id: str) -> List[Dict[str, Any]]:
    wanted = str(trace_id or "").strip()
    if not wanted:
        return []
    return [
        event
        for event in load_audit_events(workspace_root)
        if str(event.get("trace_id") or "").strip() == wanted
    ]


def query_recent_events(workspace_root: str, limit: int = 20) -> List[Dict[str, Any]]:
    events = load_audit_events(workspace_root)
    return events[-_normalize_limit(limit):]


def query_recent_problem_events(workspace_root: str, limit: int = 20) -> List[Dict[str, Any]]:
    problems = [
        event
        for event in load_audit_events(workspace_root)
        if _is_problem_event(event)
    ]
    return problems[-_normalize_limit(limit):]


def _is_problem_event(event: Dict[str, Any]) -> bool:
    if not isinstance(event, dict):
        return False
    if str(event.get("error") or "").strip():
        return True
    for key in ("status", "execution_status", "policy_decision"):
        value = str(event.get(key) or "").strip().lower()
        if value in PROBLEM_STATUSES:
            return True
    return False


def _normalize_limit(limit: int) -> int:
    try:
        value = int(limit)
    except Exception:
        value = 20
    return max(1, min(value, 1000))


def main() -> int:
    parser = argparse.ArgumentParser(description="Query ZERO task audit JSONL.")
    parser.add_argument("--workspace", default="workspace", help="Workspace root containing audit/task_audit.jsonl")
    parser.add_argument("--task-id", default="", help="Return events for a task_id")
    parser.add_argument("--trace-id", default="", help="Return events for a trace_id")
    parser.add_argument("--recent", type=int, default=0, help="Return the most recent N events")
    parser.add_argument("--problems", type=int, default=0, help="Return the most recent error/failed/blocked events")
    args = parser.parse_args()

    if args.task_id:
        result = query_events_by_task_id(args.workspace, args.task_id)
    elif args.trace_id:
        result = query_events_by_trace_id(args.workspace, args.trace_id)
    elif args.problems:
        result = query_recent_problem_events(args.workspace, limit=args.problems)
    else:
        result = query_recent_events(args.workspace, limit=args.recent or 20)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
