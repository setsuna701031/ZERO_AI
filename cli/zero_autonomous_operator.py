from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from core.runtime.runtime_autonomous_operator_bridge import (
    RuntimeAutonomousOperatorBridge,
)


ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA = "zero.autonomous_operator_cli.v1"
_DEFAULT_QUEUE_PATH = "workspace/autonomous_operator/queue.json"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _read_queue(path: str | Path) -> list[dict[str, Any]]:
    queue_path = Path(path)
    if not queue_path.exists():
        return []

    try:
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return [
            dict(item)
            for item in payload.get("tasks") or []
            if isinstance(item, dict)
        ]

    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]

    return []


def _write_queue(path: str | Path, tasks: list[dict[str, Any]]) -> str:
    queue_path = Path(path)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        json.dumps(
            {
                "schema": ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA,
                "tasks": tasks,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    return str(queue_path)


def _bridge_from_queue(
    *,
    queue_path: str | Path,
    max_tasks: int,
    self_repair: bool,
    controlled: bool,
) -> RuntimeAutonomousOperatorBridge:
    bridge = RuntimeAutonomousOperatorBridge(
        max_tasks=max_tasks,
        self_repair=self_repair,
        controlled=controlled,
    )
    for task in _read_queue(queue_path):
        status = task.get("status")
        if status not in {"completed", "failed"}:
            bridge.queue.tasks.append(dict(task))
        else:
            bridge.queue.tasks.append(dict(task))
    return bridge


def _persist_bridge_queue(
    *,
    queue_path: str | Path,
    bridge: RuntimeAutonomousOperatorBridge,
) -> str:
    return _write_queue(queue_path, bridge.queue.snapshot())


def submit_task(
    task: str,
    *,
    queue_path: str | Path = _DEFAULT_QUEUE_PATH,
) -> dict[str, Any]:
    bridge = _bridge_from_queue(
        queue_path=queue_path,
        max_tasks=1,
        self_repair=True,
        controlled=True,
    )
    result = bridge.submit(task)
    path = _persist_bridge_queue(queue_path=queue_path, bridge=bridge)

    return {
        "schema": ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA,
        "ok": result.get("ok") is True,
        "command": "submit",
        "queue_path": path,
        "queue_depth": len(bridge.queue.tasks),
        "bridge_result": result,
        "task": result.get("task") or {},
        "denial_reason": _text(result.get("denial_reason")),
    }


def run_queue(
    *,
    queue_path: str | Path = _DEFAULT_QUEUE_PATH,
    max_tasks: int = 10,
    self_repair: bool = True,
    controlled: bool = True,
) -> dict[str, Any]:
    bridge = _bridge_from_queue(
        queue_path=queue_path,
        max_tasks=max_tasks,
        self_repair=self_repair,
        controlled=controlled,
    )
    result = bridge.run_until_idle()
    path = _persist_bridge_queue(queue_path=queue_path, bridge=bridge)

    return {
        "schema": ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA,
        "ok": result.get("ok") is True,
        "command": "run",
        "queue_path": path,
        "bridge_result": result,
        "completed_count": result.get("completed_count") or 0,
        "failed_count": result.get("failed_count") or 0,
        "queued_count": result.get("queued_count") or 0,
        "queue": result.get("queue") or [],
    }


def status_queue(
    *,
    queue_path: str | Path = _DEFAULT_QUEUE_PATH,
) -> dict[str, Any]:
    tasks = _read_queue(queue_path)
    completed = [task for task in tasks if task.get("status") == "completed"]
    failed = [task for task in tasks if task.get("status") == "failed"]
    queued = [task for task in tasks if task.get("status") == "queued"]
    running = [task for task in tasks if task.get("status") == "running"]

    return {
        "schema": ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA,
        "ok": True,
        "command": "status",
        "queue_path": str(queue_path),
        "queue_depth": len(tasks),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "queued_count": len(queued),
        "running_count": len(running),
        "queue": tasks,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero-autonomous-operator")
    parser.add_argument("--queue-path", default=_DEFAULT_QUEUE_PATH)

    commands = parser.add_subparsers(dest="command", required=True)

    submit = commands.add_parser("submit")
    submit.add_argument("task", nargs="+")

    run = commands.add_parser("run")
    run.add_argument("--max-tasks", type=int, default=10)
    run.add_argument("--no-self-repair", action="store_true")
    run.add_argument("--manual", action="store_true")

    commands.add_parser("status")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "submit":
        result = submit_task(
            " ".join(args.task),
            queue_path=args.queue_path,
        )
    elif args.command == "run":
        result = run_queue(
            queue_path=args.queue_path,
            max_tasks=args.max_tasks,
            self_repair=not args.no_self_repair,
            controlled=not args.manual,
        )
    else:
        result = status_queue(queue_path=args.queue_path)

    _print_json(result)
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA",
    "build_parser",
    "main",
    "run_queue",
    "status_queue",
    "submit_task",
]
