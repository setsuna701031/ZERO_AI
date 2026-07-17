from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

from core.runtime.runtime_autonomous_operator_bridge import (
    RuntimeAutonomousOperatorBridge,
)
from core.runtime.runtime_autonomous_sentinel import RuntimeAutonomousSentinel


ZERO_SENTINEL_CLI_SCHEMA = "zero.sentinel_cli.v1"
_DEFAULT_QUEUE_PATH = "workspace/autonomous_operator/queue.json"


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
                "schema": ZERO_SENTINEL_CLI_SCHEMA,
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
        bridge.queue.tasks.append(dict(task))
    return bridge


def start_sentinel(
    *,
    queue_path: str | Path = _DEFAULT_QUEUE_PATH,
    max_cycles: int = 10,
    self_repair: bool = True,
    controlled: bool = True,
) -> dict[str, Any]:
    bridge = _bridge_from_queue(
        queue_path=queue_path,
        max_tasks=max_cycles,
        self_repair=self_repair,
        controlled=controlled,
    )
    sentinel = RuntimeAutonomousSentinel(
        bridge=bridge,
        max_cycles=max_cycles,
    )
    result = sentinel.run()
    persisted_path = _write_queue(queue_path, bridge.queue.snapshot())

    return {
        "schema": ZERO_SENTINEL_CLI_SCHEMA,
        "ok": result.get("ok") is True,
        "command": "start",
        "sentinel_online": True,
        "queue_path": persisted_path,
        "sentinel_status": result.get("sentinel_status") or "",
        "cycle_count": result.get("cycle_count") or 0,
        "completed_count": result.get("completed_count") or 0,
        "failed_count": result.get("failed_count") or 0,
        "idle_count": result.get("idle_count") or 0,
        "sentinel_result": result,
        "queue": bridge.queue.snapshot(),
    }


def watch_sentinel(
    *,
    queue_path: str | Path = _DEFAULT_QUEUE_PATH,
    max_cycles: int = 0,
    poll_interval: float = 2.0,
    self_repair: bool = True,
    controlled: bool = True,
) -> dict[str, Any]:
    """Run the sentinel repeatedly.

    max_cycles=0 means unbounded until KeyboardInterrupt.
    Each cycle reloads the queue from disk, executes at most one queued task,
    persists queue state, and then sleeps when idle.
    """

    cycles: list[dict[str, Any]] = []
    completed_count = 0
    failed_count = 0
    idle_count = 0
    interrupted = False
    cycle_limit = max(0, int(max_cycles))

    try:
        while True:
            if cycle_limit and len(cycles) >= cycle_limit:
                break

            bridge = _bridge_from_queue(
                queue_path=queue_path,
                max_tasks=1,
                self_repair=self_repair,
                controlled=controlled,
            )
            sentinel = RuntimeAutonomousSentinel(bridge=bridge, max_cycles=1)
            result = sentinel.tick()
            persisted_path = _write_queue(queue_path, bridge.queue.snapshot())

            status = result.get("sentinel_status") or "unknown"
            if status == "completed":
                completed_count += 1
            elif status == "failed":
                failed_count += 1
            elif status == "idle":
                idle_count += 1

            cycle = {
                "cycle": len(cycles) + 1,
                "status": status,
                "ok": result.get("ok") is True,
                "queue_path": persisted_path,
                "result": result,
            }
            cycles.append(cycle)

            if status == "idle" and poll_interval > 0:
                time.sleep(float(poll_interval))

    except KeyboardInterrupt:
        interrupted = True

    ok = failed_count == 0
    if interrupted:
        watch_status = "interrupted"
    elif cycle_limit and len(cycles) >= cycle_limit:
        watch_status = "max_cycles_reached"
    else:
        watch_status = "stopped"

    return {
        "schema": ZERO_SENTINEL_CLI_SCHEMA,
        "ok": ok,
        "command": "watch",
        "sentinel_online": not interrupted,
        "watch_status": watch_status,
        "queue_path": str(queue_path),
        "cycle_count": len(cycles),
        "completed_count": completed_count,
        "failed_count": failed_count,
        "idle_count": idle_count,
        "cycles": cycles,
        "queue": _read_queue(queue_path),
    }


def status_sentinel(
    *,
    queue_path: str | Path = _DEFAULT_QUEUE_PATH,
) -> dict[str, Any]:
    tasks = _read_queue(queue_path)
    completed = [task for task in tasks if task.get("status") == "completed"]
    failed = [task for task in tasks if task.get("status") == "failed"]
    queued = [task for task in tasks if task.get("status") == "queued"]
    running = [task for task in tasks if task.get("status") == "running"]

    return {
        "schema": ZERO_SENTINEL_CLI_SCHEMA,
        "ok": True,
        "command": "status",
        "sentinel_online": False,
        "queue_path": str(queue_path),
        "queue_depth": len(tasks),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "queued_count": len(queued),
        "running_count": len(running),
        "queue": tasks,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero-sentinel")
    parser.add_argument("--queue-path", default=_DEFAULT_QUEUE_PATH)

    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start")
    start.add_argument("--max-cycles", type=int, default=10)
    start.add_argument("--no-self-repair", action="store_true")
    start.add_argument("--manual", action="store_true")

    watch = commands.add_parser("watch")
    watch.add_argument("--max-cycles", type=int, default=0)
    watch.add_argument("--poll-interval", type=float, default=2.0)
    watch.add_argument("--no-self-repair", action="store_true")
    watch.add_argument("--manual", action="store_true")

    commands.add_parser("status")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "start":
        result = start_sentinel(
            queue_path=args.queue_path,
            max_cycles=args.max_cycles,
            self_repair=not args.no_self_repair,
            controlled=not args.manual,
        )
    elif args.command == "watch":
        result = watch_sentinel(
            queue_path=args.queue_path,
            max_cycles=args.max_cycles,
            poll_interval=args.poll_interval,
            self_repair=not args.no_self_repair,
            controlled=not args.manual,
        )
    else:
        result = status_sentinel(queue_path=args.queue_path)

    _print_json(result)
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ZERO_SENTINEL_CLI_SCHEMA",
    "build_parser",
    "main",
    "start_sentinel",
    "status_sentinel",
    "watch_sentinel",
]
