from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, List, Optional

from core.control.decision_evidence_viewer import DecisionEvidenceViewer
from core.control.task_control_api import TaskControlAPI


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python main.py control")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    commands = parser.add_subparsers(dest="action", required=True)

    submit = commands.add_parser("submit")
    submit.add_argument("--title", required=True)
    submit.add_argument("--instruction", required=True)
    submit.add_argument("--task-type", default="engineering_task")
    submit.add_argument("--mode", default="")

    inspect = commands.add_parser("inspect")
    inspect.add_argument("task_id")

    monitor = commands.add_parser("monitor")
    monitor.add_argument("task_id")

    recent = commands.add_parser("list")
    recent.add_argument("--limit", type=int, default=20)

    cancel = commands.add_parser("cancel")
    cancel.add_argument("task_id")

    evidence = commands.add_parser("evidence")
    evidence.add_argument("--goal-id", default="")
    evidence.add_argument("--task-id", default="")
    return parser


def main(argv: Optional[List[str]] = None, *, api: Any = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "evidence":
        viewer = DecisionEvidenceViewer(args.repo_root)
        print(viewer.render_text(goal_id=args.goal_id, task_id=args.task_id))
        return 0

    control = api or TaskControlAPI.with_workspace(args.workspace)

    if args.action == "submit":
        result = control.submit_task(
            title=args.title,
            instruction=args.instruction,
            task_type=args.task_type,
            mode=args.mode,
        )
    elif args.action == "inspect":
        result = control.inspect_task(args.task_id)
    elif args.action == "monitor":
        result = control.monitor_task(args.task_id)
    elif args.action == "list":
        result = control.list_recent_tasks(args.limit)
    else:
        result = control.request_cancel(args.task_id)

    _print_json(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
