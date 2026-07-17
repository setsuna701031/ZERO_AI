from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from core.runtime.runtime_session_queue import load_scheduler_state
from core.runtime.runtime_worker_service import (create_worker_state, load_worker_state, request_worker_action,
    run_runtime_worker, save_worker_state, worker_health)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero-runtime-worker"); commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init"); init.add_argument("--scheduler-state", required=True); init.add_argument("--worker-state", required=True); init.add_argument("--worker-name", required=True); init.add_argument("--target-root"); init.add_argument("--now")
    run = commands.add_parser("run"); run.add_argument("--scheduler-state", required=True); run.add_argument("--worker-state", required=True); run.add_argument("--worker-name", required=True); run.add_argument("--target-root", required=True); run.add_argument("--workspace-root", required=True); run.add_argument("--poll-interval", type=float, default=1.0); run.add_argument("--lease-seconds", type=int, default=30); bounds = run.add_mutually_exclusive_group(); bounds.add_argument("--once", action="store_true"); bounds.add_argument("--max-iterations", type=int); run.add_argument("--idle-exit-after", type=int); run.add_argument("--now")
    for name in ("status", "pause", "resume", "stop"):
        item = commands.add_parser(name); item.add_argument("worker_state"); item.add_argument("--now")
    health = commands.add_parser("health"); health.add_argument("worker_state"); health.add_argument("--scheduler-state"); health.add_argument("--now")
    return parser

def projection(state: dict[str, Any]) -> dict[str, Any]:
    return {key: state.get(key) for key in ("contract", "worker_id", "worker_status", "scheduler_id", "last_heartbeat_at",
        "current_session_id", "current_lease", "loop_iteration", "successful_dispatches", "waiting_dispatches",
        "blocked_dispatches", "failed_dispatches", "critical_failures", "stop_requested", "pause_requested", "failure")}

def run_cli(argv: Sequence[str] | None = None) -> tuple[dict[str, Any], int]:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            state = create_worker_state(scheduler_state_path=args.scheduler_state, worker_state_path=args.worker_state, worker_name=args.worker_name, target_root=args.target_root, now=args.now)
            state = save_worker_state(state, args.worker_state)
        elif args.command == "run":
            if args.once and args.idle_exit_after is not None: raise ValueError("once_conflicts_with_idle_exit")
            state = run_runtime_worker(scheduler_state_path=args.scheduler_state, worker_state_path=args.worker_state, worker_name=args.worker_name,
                target_root=args.target_root, workspace_root=args.workspace_root, poll_interval_seconds=args.poll_interval,
                lease_seconds=args.lease_seconds, max_iterations=1 if args.once else args.max_iterations, idle_exit_after=args.idle_exit_after,
                now_provider=(lambda: args.now) if args.now else None, sleep_provider=(lambda _: None) if args.now else None)
        elif args.command == "status": state = load_worker_state(args.worker_state)
        elif args.command == "health":
            state = load_worker_state(args.worker_state); scheduler = load_scheduler_state(args.scheduler_state) if args.scheduler_state else None
            result = worker_health(state, scheduler_state=scheduler, now=args.now); return result, 0 if result["healthy"] else 1
        else:
            state = request_worker_action(load_worker_state(args.worker_state), args.command, now=args.now); state = save_worker_state(state, args.worker_state)
        output = projection(state); status = state.get("worker_status")
        return output, 3 if status == "failed" else 1 if status in {"paused", "blocked"} else 0
    except ValueError as exc:
        message = str(exc); code = 4 if any(word in message for word in ("fingerprint", "identity", "lease", "tamper", "mismatch")) else 2
        return {"ok": False, "error": message}, code

def main(argv: Sequence[str] | None = None) -> int:
    result, code = run_cli(argv); print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return code

if __name__ == "__main__": raise SystemExit(main())
__all__ = ["build_parser", "main", "projection", "run_cli"]
